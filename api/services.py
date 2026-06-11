"""
快照计算核心服务
核心逻辑：按日期从记录表中动态计算出该日期的状态，使用内存汇总避免频繁数据库聚合
"""
from datetime import datetime, timedelta, date as date_type
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from collections import defaultdict
from .models import (
    Pen, InspectionItem, InspectionRecord, InspectionItemValue,
    FeedingRecord, CleaningRecord, Incident, IncidentUpdate
)


class SnapshotService:
    """快照计算服务"""

    @staticmethod
    def _get_date_range(target_date):
        """获取日期的时间范围：当天 00:00:00 到次日 00:00:00"""
        if isinstance(target_date, str):
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        start_dt = timezone.make_aware(start_dt)
        end_dt = timezone.make_aware(end_dt)
        return target_date, start_dt, end_dt

    @staticmethod
    def _get_active_pens():
        """获取所有活跃的栏区"""
        return Pen.objects.filter(is_active=True).order_by('code')

    @staticmethod
    def _get_active_inspection_items():
        """获取所有活跃的巡检项"""
        return InspectionItem.objects.filter(is_active=True).order_by('sort_order', 'code')

    @classmethod
    def calculate_daily_snapshot(cls, target_date, pen_id=None):
        """
        计算指定日期的快照
        核心逻辑：
        1. 查询当日所有相关记录（巡检、喂养、清洁、异常）
        2. 内存中按栏区汇总统计
        3. 计算巡检完成率（完成的巡检项数 / 总巡检项数）
        4. 返回每个栏区的完整状态快照

        注意：使用 select_related 和 prefetch_related 优化查询，然后在内存中聚合
        """
        target_date, start_dt, end_dt = cls._get_date_range(target_date)

        pens = cls._get_active_pens()
        if pen_id:
            pens = pens.filter(id=pen_id)

        pen_ids = list(pens.values_list('id', flat=True))

        if not pen_ids:
            return {
                'date': target_date.isoformat(),
                'total_pens': 0,
                'snapshot_time': timezone.now().isoformat(),
                'pen_snapshots': []
            }

        total_inspection_items = cls._get_active_inspection_items().count()

        inspection_records = InspectionRecord.objects.filter(
            pen_id__in=pen_ids,
            inspection_time__gte=start_dt,
            inspection_time__lt=end_dt
        ).select_related('pen', 'inspector').prefetch_related(
            'item_values__inspection_item'
        )

        feeding_records = FeedingRecord.objects.filter(
            pen_id__in=pen_ids,
            feeding_time__gte=start_dt,
            feeding_time__lt=end_dt
        ).select_related('pen', 'feeder')

        cleaning_records = CleaningRecord.objects.filter(
            pen_id__in=pen_ids,
            cleaning_time__gte=start_dt,
            cleaning_time__lt=end_dt
        ).select_related('pen', 'cleaner')

        incidents = Incident.objects.filter(
            pen_id__in=pen_ids
        ).filter(
            Q(incident_time__gte=start_dt, incident_time__lt=end_dt) |
            Q(status__in=['OPEN', 'IN_PROGRESS'], incident_time__lt=end_dt)
        ).select_related('pen', 'reporter', 'handler').prefetch_related('updates')

        inspection_by_pen = defaultdict(list)
        for record in inspection_records:
            inspection_by_pen[record.pen_id].append(record)

        feeding_by_pen = defaultdict(list)
        for record in feeding_records:
            feeding_by_pen[record.pen_id].append(record)

        cleaning_by_pen = defaultdict(list)
        for record in cleaning_records:
            cleaning_by_pen[record.pen_id].append(record)

        incidents_by_pen = defaultdict(list)
        for incident in incidents:
            status_at_date = cls._get_incident_status_at_date(incident, target_date)
            if status_at_date:
                incidents_by_pen[incident.pen_id].append({
                    'incident': incident,
                    'status_at_date': status_at_date
                })

        pen_snapshots = []
        for pen in pens:
            pen_inspections = inspection_by_pen.get(pen.id, [])
            pen_feedings = feeding_by_pen.get(pen.id, [])
            pen_cleanings = cleaning_by_pen.get(pen.id, [])
            pen_incidents_data = incidents_by_pen.get(pen.id, [])

            completed_item_count = 0
            abnormal_items = []
            inspected_items_set = set()

            for record in pen_inspections:
                for item_value in record.item_values.all():
                    if item_value.inspection_item_id not in inspected_items_set:
                        inspected_items_set.add(item_value.inspection_item_id)
                        completed_item_count += 1
                    if item_value.is_abnormal:
                        abnormal_items.append({
                            'inspection_item_id': item_value.inspection_item_id,
                            'inspection_item_code': item_value.inspection_item.code,
                            'inspection_item_name': item_value.inspection_item.name,
                            'value': item_value.get_display_value(),
                            'record_time': record.inspection_time.isoformat()
                        })

            inspection_completion_rate = 0.0
            if total_inspection_items > 0:
                inspection_completion_rate = round(completed_item_count / total_inspection_items * 100, 2)

            total_feed_amount = sum(r.feed_amount for r in pen_feedings)

            open_incidents = []
            in_progress_incidents = []
            resolved_incidents = []
            new_incidents_today = []

            for data in pen_incidents_data:
                incident = data['incident']
                status = data['status_at_date']

                incident_info = {
                    'id': incident.id,
                    'title': incident.title,
                    'description': incident.description,
                    'severity': incident.severity,
                    'severity_display': incident.get_severity_display(),
                    'status': status,
                    'status_display': dict(Incident.Status.choices)[status],
                    'incident_time': incident.incident_time.isoformat(),
                    'reporter_name': incident.reporter.real_name,
                }

                is_new_today = start_dt <= incident.incident_time < end_dt

                if status in [Incident.Status.OPEN, Incident.Status.IN_PROGRESS]:
                    if is_new_today:
                        new_incidents_today.append(incident_info)
                    if status == Incident.Status.OPEN:
                        open_incidents.append(incident_info)
                    else:
                        in_progress_incidents.append(incident_info)
                elif status in [Incident.Status.RESOLVED, Incident.Status.CLOSED]:
                    if is_new_today or (incident.resolved_time and
                                        start_dt <= incident.resolved_time < end_dt):
                        resolved_incidents.append(incident_info)

            total_abnormal_count = len(abnormal_items) + len(new_incidents_today)

            pen_snapshot = {
                'pen_id': pen.id,
                'pen_code': pen.code,
                'pen_name': pen.name,
                'livestock_type': pen.livestock_type,
                'current_count': pen.current_count,
                'capacity': pen.capacity,
                'inspection': {
                    'total_items': total_inspection_items,
                    'completed_items': completed_item_count,
                    'completion_rate': inspection_completion_rate,
                    'inspection_count': len(pen_inspections),
                    'inspectors': list(set(r.inspector.real_name for r in pen_inspections)),
                    'abnormal_items': abnormal_items,
                    'abnormal_count': len(abnormal_items)
                },
                'feeding': {
                    'feeding_count': len(pen_feedings),
                    'total_feed_amount': round(total_feed_amount, 2),
                    'feed_types': list(set(r.feed_type for r in pen_feedings)),
                    'last_feeding_time': max(
                        (r.feeding_time for r in pen_feedings),
                        default=None
                    ).isoformat() if pen_feedings else None
                },
                'cleaning': {
                    'cleaning_count': len(pen_cleanings),
                    'cleaning_types': list(set(r.get_cleaning_type_display() for r in pen_cleanings)),
                    'total_duration_minutes': sum(r.duration_minutes for r in pen_cleanings),
                    'last_cleaning_time': max(
                        (r.cleaning_time for r in pen_cleanings),
                        default=None
                    ).isoformat() if pen_cleanings else None
                },
                'incidents': {
                    'open_count': len(open_incidents),
                    'in_progress_count': len(in_progress_incidents),
                    'resolved_today_count': len(resolved_incidents),
                    'new_today_count': len(new_incidents_today),
                    'total_abnormal_count': total_abnormal_count,
                    'open_incidents': open_incidents,
                    'in_progress_incidents': in_progress_incidents,
                    'resolved_today_incidents': resolved_incidents,
                    'new_today_incidents': new_incidents_today,
                },
                'overall_status': cls._calculate_overall_status(
                    inspection_completion_rate,
                    len(open_incidents),
                    len(abnormal_items)
                )
            }
            pen_snapshots.append(pen_snapshot)

        total_open_incidents = sum(s['incidents']['open_count'] for s in pen_snapshots)
        total_abnormal = sum(s['incidents']['total_abnormal_count'] for s in pen_snapshots)
        avg_completion_rate = round(
            sum(s['inspection']['completion_rate'] for s in pen_snapshots) / len(pen_snapshots),
            2
        ) if pen_snapshots else 0.0

        return {
            'date': target_date.isoformat(),
            'total_pens': len(pen_snapshots),
            'snapshot_time': timezone.now().isoformat(),
            'average_inspection_completion_rate': avg_completion_rate,
            'total_open_incidents': total_open_incidents,
            'total_abnormal_count': total_abnormal,
            'pen_snapshots': pen_snapshots
        }

    @staticmethod
    def _get_incident_status_at_date(incident, target_date):
        """计算异常事件在指定日期的状态"""
        target_end = datetime.combine(target_date, datetime.max.time())

        if incident.incident_time.date() > target_date:
            return None

        if not incident.resolved_time:
            return incident.status

        if incident.resolved_time.date() <= target_date:
            return incident.status

        last_update_before = None
        for update in incident.updates.all().order_by('created_at'):
            if update.created_at.date() <= target_date:
                last_update_before = update

        if last_update_before:
            return last_update_before.new_status

        if incident.created_at.date() <= target_date:
            return Incident.Status.OPEN

        return None

    @staticmethod
    def _calculate_duration(incident):
        """计算事件持续时间（小时）"""
        if incident.resolved_time:
            duration = incident.resolved_time - incident.incident_time
            return round(duration.total_seconds() / 3600, 2)
        duration = timezone.now() - incident.incident_time
        return round(duration.total_seconds() / 3600, 2)

    @staticmethod
    def _calculate_overall_status(completion_rate, open_incidents, abnormal_items):
        """计算栏区整体状态"""
        if open_incidents > 0 or abnormal_items > 0:
            return 'WARNING'
        if completion_rate < 80:
            return 'ATTENTION'
        if completion_rate >= 100:
            return 'NORMAL'
        return 'PARTIAL'

    @classmethod
    def compare_snapshots(cls, date1, date2, pen_id=None):
        """
        对比两个日期的快照，返回差异
        用于：历史快照与当前数据差异对比、巡检完成率变化趋势等
        """
        snapshot1 = cls.calculate_daily_snapshot(date1, pen_id)
        snapshot2 = cls.calculate_daily_snapshot(date2, pen_id)

        comparison = {
            'date1': snapshot1['date'],
            'date2': snapshot2['date'],
            'summary': {
                'completion_rate_change': round(
                    snapshot2['average_inspection_completion_rate'] - snapshot1['average_inspection_completion_rate'],
                    2
                ),
                'open_incidents_change': snapshot2['total_open_incidents'] - snapshot1['total_open_incidents'],
                'abnormal_count_change': snapshot2['total_abnormal_count'] - snapshot1['total_abnormal_count'],
            },
            'pen_comparisons': []
        }

        pen_map1 = {s['pen_id']: s for s in snapshot1['pen_snapshots']}
        pen_map2 = {s['pen_id']: s for s in snapshot2['pen_snapshots']}

        all_pen_ids = set(pen_map1.keys()) | set(pen_map2.keys())

        for pen_id in sorted(all_pen_ids):
            s1 = pen_map1.get(pen_id)
            s2 = pen_map2.get(pen_id)

            if not s1 or not s2:
                continue

            pen_comp = {
                'pen_id': pen_id,
                'pen_code': s2['pen_code'],
                'pen_name': s2['pen_name'],
                'differences': {
                    'inspection_completion_rate': {
                        'old': s1['inspection']['completion_rate'],
                        'new': s2['inspection']['completion_rate'],
                        'change': round(s2['inspection']['completion_rate'] - s1['inspection']['completion_rate'], 2)
                    },
                    'feeding_count': {
                        'old': s1['feeding']['feeding_count'],
                        'new': s2['feeding']['feeding_count'],
                        'change': s2['feeding']['feeding_count'] - s1['feeding']['feeding_count']
                    },
                    'cleaning_count': {
                        'old': s1['cleaning']['cleaning_count'],
                        'new': s2['cleaning']['cleaning_count'],
                        'change': s2['cleaning']['cleaning_count'] - s1['cleaning']['cleaning_count']
                    },
                    'open_incidents': {
                        'old': s1['incidents']['open_count'],
                        'new': s2['incidents']['open_count'],
                        'change': s2['incidents']['open_count'] - s1['incidents']['open_count']
                    },
                    'new_incidents': {
                        'old': s1['incidents']['new_today_count'],
                        'new': s2['incidents']['new_today_count'],
                        'change': s2['incidents']['new_today_count'] - s1['incidents']['new_today_count']
                    }
                },
                'status_changed': s1['overall_status'] != s2['overall_status'],
                'old_status': s1['overall_status'],
                'new_status': s2['overall_status']
            }
            comparison['pen_comparisons'].append(pen_comp)

        return comparison

    @classmethod
    def get_trend_data(cls, start_date, end_date, pen_id=None, metric='completion_rate'):
        """
        获取指定时间范围内的趋势数据
        用于展示变化趋势，如过去一周巡检完成率的变化
        """
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        trend_data = []
        current_date = start_date

        while current_date <= end_date:
            snapshot = cls.calculate_daily_snapshot(current_date, pen_id)

            if metric == 'completion_rate':
                value = snapshot['average_inspection_completion_rate']
            elif metric == 'open_incidents':
                value = snapshot['total_open_incidents']
            elif metric == 'abnormal_count':
                value = snapshot['total_abnormal_count']
            elif metric == 'feeding_count':
                value = sum(s['feeding']['feeding_count'] for s in snapshot['pen_snapshots'])
            elif metric == 'cleaning_count':
                value = sum(s['cleaning']['cleaning_count'] for s in snapshot['pen_snapshots'])
            else:
                value = 0

            trend_data.append({
                'date': current_date.isoformat(),
                'value': value,
                'snapshot_summary': {
                    'average_completion_rate': snapshot['average_inspection_completion_rate'],
                    'total_open_incidents': snapshot['total_open_incidents'],
                    'total_abnormal_count': snapshot['total_abnormal_count'],
                    'total_pens': snapshot['total_pens']
                }
            })

            current_date += timedelta(days=1)

        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'metric': metric,
            'trend_data': trend_data
        }

    @classmethod
    def get_incident_timeline(cls, incident_id):
        """
        获取异常事件的完整时间线
        展示从发生到关闭的全过程
        """
        try:
            incident = Incident.objects.select_related(
                'pen', 'reporter', 'handler'
            ).prefetch_related('updates__operator').get(id=incident_id)
        except Incident.DoesNotExist:
            return None

        timeline = []

        timeline.append({
            'timestamp': incident.incident_time.isoformat(),
            'event_type': 'CREATED',
            'event_description': '事件上报',
            'operator': incident.reporter.real_name,
            'details': {
                'title': incident.title,
                'description': incident.description,
                'severity': incident.severity,
                'severity_display': incident.get_severity_display(),
                'status': Incident.Status.OPEN,
                'status_display': '待处理'
            }
        })

        for update in incident.updates.order_by('created_at'):
            timeline.append({
                'timestamp': update.created_at.isoformat(),
                'event_type': 'STATUS_CHANGED',
                'event_description': f'{update.get_old_status_display()} → {update.get_new_status_display()}',
                'operator': update.operator.real_name,
                'details': {
                    'old_status': update.old_status,
                    'old_status_display': update.get_old_status_display(),
                    'new_status': update.new_status,
                    'new_status_display': update.get_new_status_display(),
                    'comment': update.comment
                }
            })

        if incident.resolved_time:
            timeline.append({
                'timestamp': incident.resolved_time.isoformat(),
                'event_type': 'RESOLVED',
                'event_description': '事件解决',
                'operator': incident.handler.real_name if incident.handler else '系统',
                'details': {
                    'resolution': incident.resolution,
                    'status': incident.status,
                    'status_display': incident.get_status_display()
                }
            })

        timeline.sort(key=lambda x: x['timestamp'])

        return {
            'incident_id': incident.id,
            'pen_code': incident.pen.code,
            'pen_name': incident.pen.name,
            'title': incident.title,
            'description': incident.description,
            'severity': incident.severity,
            'severity_display': incident.get_severity_display(),
            'current_status': incident.status,
            'current_status_display': incident.get_status_display(),
            'total_duration_hours': cls._calculate_duration(incident),
            'timeline': timeline
        }


snapshot_service = SnapshotService()
