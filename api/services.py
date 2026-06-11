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
    FeedingRecord, CleaningRecord, Incident, IncidentUpdate, DailySnapshot
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
        target_date, start_dt, end_dt = cls._get_date_range(target_date)
        pen_filter_key = str(pen_id) if pen_id else 'all'

        today = timezone.now().date()
        if target_date < today:
            saved_snapshot = DailySnapshot.objects.filter(
                snapshot_date=target_date,
                pen_filter_key=pen_filter_key
            ).first()
            if saved_snapshot:
                return saved_snapshot.data

            snapshot = cls._calculate_daily_snapshot(target_date, start_dt, end_dt, pen_id)
            saved_snapshot, _ = DailySnapshot.objects.get_or_create(
                snapshot_date=target_date,
                pen_filter_key=pen_filter_key,
                defaults={'data': snapshot}
            )
            return saved_snapshot.data

        snapshot = cls._calculate_daily_snapshot(target_date, start_dt, end_dt, pen_id)
        if target_date == today:
            DailySnapshot.objects.update_or_create(
                snapshot_date=target_date,
                pen_filter_key=pen_filter_key,
                defaults={'data': snapshot}
            )
        return snapshot

    @classmethod
    def _calculate_daily_snapshot(cls, target_date, start_dt, end_dt, pen_id=None):
        """
        计算指定日期的快照
        核心逻辑：
        1. 查询当日所有相关记录（巡检、喂养、清洁、异常）
        2. 内存中按栏区汇总统计
        3. 计算巡检完成率（完成的巡检项数 / 总巡检项数）
        4. 返回每个栏区的完整状态快照

        注意：使用 select_related 和 prefetch_related 优化查询，然后在内存中聚合
        """
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
            incident_time__lt=end_dt
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
                'health_score': None,
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
            from .models import HealthScoreRecord
            try:
                score_record = HealthScoreRecord.objects.filter(
                    score_date=target_date,
                    pen_id=pen.id
                ).first()
                if score_record:
                    pen_snapshot['health_score'] = {
                        'total_score': score_record.total_score,
                        'risk_level': score_record.risk_level,
                        'risk_level_display': score_record.get_risk_level_display(),
                        'deduction': score_record.deduction,
                        'addition': score_record.addition,
                    }
            except Exception:
                pass

            pen_snapshots.append(pen_snapshot)

        total_open_incidents = sum(s['incidents']['open_count'] for s in pen_snapshots)
        total_abnormal = sum(s['incidents']['total_abnormal_count'] for s in pen_snapshots)
        avg_completion_rate = round(
            sum(s['inspection']['completion_rate'] for s in pen_snapshots) / len(pen_snapshots),
            2
        ) if pen_snapshots else 0.0

        avg_health_score = 0.0
        health_score_count = 0
        risk_distribution = {}
        for s in pen_snapshots:
            if s['health_score'] and s['health_score']['total_score'] is not None:
                avg_health_score += s['health_score']['total_score']
                health_score_count += 1
                risk_level = s['health_score']['risk_level_display']
                risk_distribution[risk_level] = risk_distribution.get(risk_level, 0) + 1
        if health_score_count > 0:
            avg_health_score = round(avg_health_score / health_score_count, 2)

        return {
            'date': target_date.isoformat(),
            'total_pens': len(pen_snapshots),
            'snapshot_time': timezone.now().isoformat(),
            'average_inspection_completion_rate': avg_completion_rate,
            'total_open_incidents': total_open_incidents,
            'total_abnormal_count': total_abnormal,
            'average_health_score': avg_health_score,
            'health_score_risk_distribution': risk_distribution,
            'pen_snapshots': pen_snapshots
        }

    @staticmethod
    def _get_incident_status_at_date(incident, target_date):
        """
        计算异常事件在指定日期的状态
        通过 IncidentUpdate 记录来还原历史状态，确保快照准确
        """
        target_end = datetime.combine(target_date, datetime.max.time())
        target_end = timezone.make_aware(target_end)

        if incident.incident_time > target_end:
            return None

        last_update_before = None
        for update in incident.updates.all().order_by('created_at'):
            if update.created_at <= target_end:
                last_update_before = update

        if last_update_before:
            return last_update_before.new_status

        if incident.incident_time <= target_end:
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


class HealthScoreService:
    """健康评分计算服务"""

    DEFAULT_DIMENSION_CONFIGS = [
        {'dimension_key': 'inspection_abnormal', 'weight': 30, 'sort_order': 1},
        {'dimension_key': 'open_incidents', 'weight': 25, 'sort_order': 2},
        {'dimension_key': 'feeding_completion', 'weight': 15, 'sort_order': 3},
        {'dimension_key': 'cleaning_completion', 'weight': 15, 'sort_order': 4},
        {'dimension_key': 'capacity_ratio', 'weight': 15, 'sort_order': 5},
    ]

    DEFAULT_RISK_THRESHOLDS = [
        {'risk_level': 'EXCELLENT', 'min_score': 90, 'max_score': 101, 'color': '#00C853', 'description': '状态优秀，一切正常'},
        {'risk_level': 'GOOD', 'min_score': 75, 'max_score': 90, 'color': '#64DD17', 'description': '状态良好，需保持'},
        {'risk_level': 'NORMAL', 'min_score': 60, 'max_score': 75, 'color': '#FFD600', 'description': '状态一般，需关注'},
        {'risk_level': 'WARNING', 'min_score': 40, 'max_score': 60, 'color': '#FF9100', 'description': '存在风险，需整改'},
        {'risk_level': 'DANGER', 'min_score': 0, 'max_score': 40, 'color': '#FF1744', 'description': '严重风险，需立即处理'},
    ]

    @classmethod
    def initialize_default_configs(cls):
        """初始化默认配置（如果不存在）"""
        for config in cls.DEFAULT_DIMENSION_CONFIGS:
            from .models import HealthScoreConfig
            HealthScoreConfig.objects.get_or_create(
                dimension_key=config['dimension_key'],
                defaults={
                    'weight': config['weight'],
                    'sort_order': config['sort_order'],
                    'is_enabled': True
                }
            )

        for threshold in cls.DEFAULT_RISK_THRESHOLDS:
            from .models import HealthScoreRiskThreshold
            HealthScoreRiskThreshold.objects.get_or_create(
                risk_level=threshold['risk_level'],
                defaults={
                    'min_score': threshold['min_score'],
                    'max_score': threshold['max_score'],
                    'color': threshold['color'],
                    'description': threshold['description']
                }
            )

        from .models import HealthScoreInspectionItem, InspectionItem
        active_items = InspectionItem.objects.filter(is_active=True)
        for item in active_items:
            HealthScoreInspectionItem.objects.get_or_create(
                inspection_item=item,
                defaults={
                    'penalty_per_abnormal': 5.0,
                    'is_enabled': True
                }
            )

    @classmethod
    def _get_date_range(cls, target_date):
        from datetime import datetime, timedelta
        if isinstance(target_date, str):
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        from django.utils import timezone
        start_dt = timezone.make_aware(start_dt)
        end_dt = timezone.make_aware(end_dt)
        return target_date, start_dt, end_dt

    @classmethod
    def _get_active_pens(cls):
        from .models import Pen
        return Pen.objects.filter(is_active=True).order_by('code')

    @classmethod
    def _get_enabled_dimensions(cls):
        from .models import HealthScoreConfig
        return HealthScoreConfig.objects.filter(is_enabled=True)

    @classmethod
    def _get_risk_level(cls, score):
        from .models import HealthScoreRiskThreshold
        thresholds = HealthScoreRiskThreshold.objects.all().order_by('-min_score')
        for threshold in thresholds:
            if threshold.min_score <= score < threshold.max_score:
                return threshold.risk_level
        return 'NORMAL'

    @classmethod
    def _get_incident_status_at_date(cls, incident, target_date):
        """
        计算异常事件在指定日期的状态（基于 IncidentUpdate 历史记录）
        与 SnapshotService 保持一致，确保历史评分准确
        """
        from datetime import datetime
        from django.utils import timezone
        target_end = datetime.combine(target_date, datetime.max.time())
        target_end = timezone.make_aware(target_end)

        if incident.incident_time > target_end:
            return None

        last_update_before = None
        for update in incident.updates.all().order_by('created_at'):
            if update.created_at <= target_end:
                last_update_before = update

        if last_update_before:
            return last_update_before.new_status

        if incident.resolved_time and incident.resolved_time <= target_end:
            return incident.status

        if incident.incident_time <= target_end:
            return 'OPEN'

        return None

    @classmethod
    def _is_resolved_on_date(cls, incident, target_date):
        """判断事件是否在指定日期当天被解决/关闭"""
        from datetime import datetime, timedelta
        from django.utils import timezone

        if isinstance(target_date, str):
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        start_dt = timezone.make_aware(start_dt)
        end_dt = timezone.make_aware(end_dt)

        if incident.resolved_time and start_dt <= incident.resolved_time < end_dt:
            return True

        for update in incident.updates.all().order_by('created_at'):
            if start_dt <= update.created_at < end_dt:
                if update.new_status in ['RESOLVED', 'CLOSED']:
                    return True

        return False

    @classmethod
    def calculate_pen_score(cls, pen, target_date):
        """计算单个栏区在指定日期的健康评分"""
        from .models import (
            InspectionRecord, InspectionItemValue, FeedingRecord,
            CleaningRecord, Incident, HealthScoreInspectionItem,
            HealthScoreRecord, HealthScoreDetail
        )

        target_date, start_dt, end_dt = cls._get_date_range(target_date)
        dimensions = cls._get_enabled_dimensions()
        dim_map = {d.dimension_key: d for d in dimensions}

        total_weight = sum(d.weight for d in dimensions)
        if total_weight == 0:
            total_weight = 100

        base_score = 100.0
        total_deduction = 0.0
        total_addition = 0.0
        dimension_scores = {}
        dimension_counts = {}

        score_details_data = []

        # 1. 巡检异常扣分
        if 'inspection_abnormal' in dim_map:
            dim_weight = dim_map['inspection_abnormal'].weight
            weighted_base = base_score * (dim_weight / total_weight)

            abnormal_items = InspectionItemValue.objects.filter(
                is_abnormal=True,
                record__pen=pen,
                record__inspection_time__gte=start_dt,
                record__inspection_time__lt=end_dt
            ).select_related('inspection_item', 'record')

            enabled_items = HealthScoreInspectionItem.objects.filter(
                is_enabled=True
            ).values_list('inspection_item_id', 'penalty_per_abnormal')
            penalty_map = dict(enabled_items)

            abnormal_count = 0
            inspection_deduction = 0.0

            for item_value in abnormal_items:
                if item_value.inspection_item_id not in penalty_map:
                    continue
                abnormal_count += 1
                penalty = penalty_map[item_value.inspection_item_id]
                actual_deduction = min(penalty * (dim_weight / 100), weighted_base / max(abnormal_count, 1))
                inspection_deduction += actual_deduction

                score_details_data.append({
                    'score_type': 'DEDUCTION',
                    'source_type': 'inspection_abnormal',
                    'score_value': round(actual_deduction, 2),
                    'description': f'巡检异常: {item_value.inspection_item.name} = {item_value.get_display_value()}',
                    'source_id': item_value.record_id,
                    'inspection_item': item_value.inspection_item,
                    'incident': None,
                    'rectification_status': 'pending',
                })

            dimension_scores['inspection_abnormal_score'] = round(max(0, weighted_base - inspection_deduction), 2)
            dimension_counts['inspection_abnormal_count'] = abnormal_count
            total_deduction += inspection_deduction

        # 2. 未处理异常事件扣分（按历史日期状态计算）
        if 'open_incidents' in dim_map:
            dim_weight = dim_map['open_incidents'].weight
            weighted_base = base_score * (dim_weight / total_weight)

            all_incidents = Incident.objects.filter(
                pen=pen,
                incident_time__lt=end_dt
            ).select_related('reporter', 'handler').prefetch_related('updates')

            open_incidents = []
            for incident in all_incidents:
                status_at_date = cls._get_incident_status_at_date(incident, target_date)
                if status_at_date in ['OPEN', 'IN_PROGRESS']:
                    open_incidents.append(incident)

            open_count = len(open_incidents)
            incidents_deduction = 0.0
            penalty_per_incident = 10.0 * (dim_weight / 100)

            for incident in open_incidents:
                severity_multiplier = {
                    'LOW': 0.5,
                    'MEDIUM': 1.0,
                    'HIGH': 1.5,
                    'CRITICAL': 2.0
                }.get(incident.severity, 1.0)

                deduction = min(penalty_per_incident * severity_multiplier, weighted_base / max(open_count, 1))
                incidents_deduction += deduction

                score_details_data.append({
                    'score_type': 'DEDUCTION',
                    'source_type': 'open_incident',
                    'score_value': round(deduction, 2),
                    'description': f'未处理事件[{incident.get_severity_display()}]: {incident.title}',
                    'source_id': incident.id,
                    'inspection_item': None,
                    'incident': incident,
                    'rectification_status': 'pending',
                })

            dimension_scores['open_incidents_score'] = round(max(0, weighted_base - incidents_deduction), 2)
            dimension_counts['open_incidents_count'] = open_count
            total_deduction += incidents_deduction

        # 3. 喂养完成情况得分
        if 'feeding_completion' in dim_map:
            dim_weight = dim_map['feeding_completion'].weight
            weighted_base = base_score * (dim_weight / total_weight)

            feeding_records = FeedingRecord.objects.filter(
                pen=pen,
                feeding_time__gte=start_dt,
                feeding_time__lt=end_dt
            )
            feeding_count = feeding_records.count()
            expected_feeding = 2
            feeding_rate = min(feeding_count / expected_feeding * 100, 100) if expected_feeding > 0 else 100
            feeding_score = weighted_base * (feeding_rate / 100)

            if feeding_rate < 100:
                deduction = weighted_base - feeding_score
                score_details_data.append({
                    'score_type': 'DEDUCTION',
                    'source_type': 'feeding_incomplete',
                    'score_value': round(deduction, 2),
                    'description': f'喂养未完成: {feeding_count}/{expected_feeding} 次',
                    'source_id': None,
                    'inspection_item': None,
                    'incident': None,
                    'rectification_status': 'pending',
                })
                total_deduction += deduction

            dimension_scores['feeding_completion_score'] = round(feeding_score, 2)
            dimension_counts['feeding_completion_rate'] = round(feeding_rate, 2)

        # 4. 清洁完成情况得分
        if 'cleaning_completion' in dim_map:
            dim_weight = dim_map['cleaning_completion'].weight
            weighted_base = base_score * (dim_weight / total_weight)

            cleaning_records = CleaningRecord.objects.filter(
                pen=pen,
                cleaning_time__gte=start_dt,
                cleaning_time__lt=end_dt
            )
            cleaning_count = cleaning_records.count()
            expected_cleaning = 1
            cleaning_rate = min(cleaning_count / expected_cleaning * 100, 100) if expected_cleaning > 0 else 100
            cleaning_score = weighted_base * (cleaning_rate / 100)

            if cleaning_rate < 100:
                deduction = weighted_base - cleaning_score
                score_details_data.append({
                    'score_type': 'DEDUCTION',
                    'source_type': 'cleaning_incomplete',
                    'score_value': round(deduction, 2),
                    'description': f'清洁未完成: {cleaning_count}/{expected_cleaning} 次',
                    'source_id': None,
                    'inspection_item': None,
                    'incident': None,
                    'rectification_status': 'pending',
                })
                total_deduction += deduction

            dimension_scores['cleaning_completion_score'] = round(cleaning_score, 2)
            dimension_counts['cleaning_completion_rate'] = round(cleaning_rate, 2)

        # 5. 存栏容量占比得分
        if 'capacity_ratio' in dim_map:
            dim_weight = dim_map['capacity_ratio'].weight
            weighted_base = base_score * (dim_weight / total_weight)

            capacity_ratio = 0
            if pen.capacity > 0:
                capacity_ratio = (pen.current_count / pen.capacity) * 100

            optimal_min = 60
            optimal_max = 90
            if optimal_min <= capacity_ratio <= optimal_max:
                capacity_score = weighted_base
            else:
                deviation = max(optimal_min - capacity_ratio, capacity_ratio - optimal_max, 0)
                penalty_ratio = min(deviation / 50, 1.0)
                capacity_score = weighted_base * (1 - penalty_ratio * 0.5)

                if penalty_ratio > 0:
                    deduction = weighted_base - capacity_score
                    status = '存栏不足' if capacity_ratio < optimal_min else '存栏过载'
                    score_details_data.append({
                        'score_type': 'DEDUCTION',
                        'source_type': 'capacity_abnormal',
                        'score_value': round(deduction, 2),
                        'description': f'{status}: 当前{pen.current_count}/容量{pen.capacity} ({round(capacity_ratio, 1)}%)',
                        'source_id': None,
                        'inspection_item': None,
                        'incident': None,
                        'rectification_status': 'pending',
                    })
                    total_deduction += deduction

            dimension_scores['capacity_ratio_score'] = round(capacity_score, 2)
            dimension_counts['capacity_ratio'] = round(capacity_ratio, 2)

        # 检查当日已解决的异常事件，添加恢复加分（按历史状态判断）
        all_incidents = Incident.objects.filter(
            pen=pen,
            incident_time__lt=end_dt
        ).select_related('reporter', 'handler').prefetch_related('updates')

        for incident in all_incidents:
            if cls._is_resolved_on_date(incident, target_date):
                recovery_score = min(3.0, 5.0)
                total_addition += recovery_score
                score_details_data.append({
                    'score_type': 'RECOVERY',
                    'source_type': 'incident_resolved',
                    'score_value': round(recovery_score, 2),
                    'description': f'异常事件已解决: {incident.title}',
                    'source_id': incident.id,
                    'inspection_item': None,
                    'incident': incident,
                    'rectification_status': 'rectified',
                })

        total_score = round(max(0, min(100, base_score - total_deduction + total_addition)), 2)
        risk_level = cls._get_risk_level(total_score)

        return {
            'pen': pen,
            'score_date': target_date,
            'base_score': round(base_score, 2),
            'total_score': total_score,
            'deduction': round(total_deduction, 2),
            'addition': round(total_addition, 2),
            'risk_level': risk_level,
            'dimension_scores': dimension_scores,
            'dimension_counts': dimension_counts,
            'details': score_details_data,
        }

    @classmethod
    def save_score_record(cls, score_data):
        """保存评分记录和明细"""
        from .models import HealthScoreRecord, HealthScoreDetail
        from django.utils import timezone

        record, created = HealthScoreRecord.objects.update_or_create(
            score_date=score_data['score_date'],
            pen=score_data['pen'],
            defaults={
                'base_score': score_data['base_score'],
                'total_score': score_data['total_score'],
                'deduction': score_data['deduction'],
                'addition': score_data['addition'],
                'risk_level': score_data['risk_level'],
                'inspection_abnormal_score': score_data['dimension_scores'].get('inspection_abnormal_score', 0),
                'open_incidents_score': score_data['dimension_scores'].get('open_incidents_score', 0),
                'feeding_completion_score': score_data['dimension_scores'].get('feeding_completion_score', 100),
                'cleaning_completion_score': score_data['dimension_scores'].get('cleaning_completion_score', 100),
                'capacity_ratio_score': score_data['dimension_scores'].get('capacity_ratio_score', 100),
                'inspection_abnormal_count': score_data['dimension_counts'].get('inspection_abnormal_count', 0),
                'open_incidents_count': score_data['dimension_counts'].get('open_incidents_count', 0),
                'feeding_completion_rate': score_data['dimension_counts'].get('feeding_completion_rate', 0),
                'cleaning_completion_rate': score_data['dimension_counts'].get('cleaning_completion_rate', 0),
                'capacity_ratio': score_data['dimension_counts'].get('capacity_ratio', 0),
                'is_calculated': True,
                'calculated_at': timezone.now(),
            }
        )

        if not created:
            record.details.all().delete()

        details_to_create = []
        for detail_data in score_data['details']:
            details_to_create.append(HealthScoreDetail(
                score_record=record,
                score_type=detail_data['score_type'],
                source_type=detail_data['source_type'],
                score_value=detail_data['score_value'],
                description=detail_data['description'],
                source_id=detail_data['source_id'],
                inspection_item=detail_data['inspection_item'],
                incident=detail_data['incident'],
                rectification_status=detail_data['rectification_status'],
                rectified_at=timezone.now() if detail_data['rectification_status'] == 'rectified' else None,
            ))

        if details_to_create:
            HealthScoreDetail.objects.bulk_create(details_to_create)

        return record

    @classmethod
    def calculate_and_save_daily_scores(cls, target_date, pen_id=None):
        """计算并保存指定日期所有栏区的健康评分"""
        cls.initialize_default_configs()
        pens = cls._get_active_pens()
        if pen_id:
            pens = pens.filter(id=pen_id)

        results = []
        for pen in pens:
            score_data = cls.calculate_pen_score(pen, target_date)
            record = cls.save_score_record(score_data)
            results.append(record)

        return results

    @classmethod
    def recalculate_on_data_change(cls, pen_id, event_date=None):
        """当巡检/喂养/清洁/异常事件数据变更时重新计算评分"""
        from django.utils import timezone
        if event_date is None:
            event_date = timezone.now().date()
        return cls.calculate_and_save_daily_scores(event_date, pen_id)

    @classmethod
    def get_score_trend(cls, start_date, end_date, pen_id=None):
        """获取评分趋势数据"""
        from datetime import timedelta
        from .models import HealthScoreRecord

        if isinstance(start_date, str):
            from datetime import datetime
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            from datetime import datetime
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        pens = cls._get_active_pens()
        if pen_id:
            pens = pens.filter(id=pen_id)

        pen_ids = list(pens.values_list('id', flat=True))

        records = HealthScoreRecord.objects.filter(
            score_date__gte=start_date,
            score_date__lte=end_date,
            pen_id__in=pen_ids
        ).select_related('pen').order_by('score_date', 'pen__code')

        from collections import defaultdict
        daily_summary = defaultdict(list)
        for record in records:
            daily_summary[record.score_date].append(record)

        trend_data = []
        current_date = start_date
        while current_date <= end_date:
            day_records = daily_summary.get(current_date, [])
            if day_records:
                avg_score = round(sum(r.total_score for r in day_records) / len(day_records), 2)
                total_deduction = round(sum(r.deduction for r in day_records), 2)
                total_addition = round(sum(r.addition for r in day_records), 2)
                by_risk = defaultdict(int)
                for r in day_records:
                    by_risk[r.risk_level] += 1
            else:
                avg_score = 0
                total_deduction = 0
                total_addition = 0
                by_risk = {}

            pen_scores = []
            for r in day_records:
                pen_scores.append({
                    'pen_id': r.pen_id,
                    'pen_code': r.pen.code,
                    'pen_name': r.pen.name,
                    'score': r.total_score,
                    'risk_level': r.risk_level,
                    'risk_level_display': r.get_risk_level_display(),
                    'deduction': r.deduction,
                    'addition': r.addition,
                })

            trend_data.append({
                'date': current_date.isoformat(),
                'average_score': avg_score,
                'total_deduction': total_deduction,
                'total_addition': total_addition,
                'pen_count': len(day_records),
                'risk_distribution': dict(by_risk),
                'pen_scores': pen_scores,
            })
            current_date += timedelta(days=1)

        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'trend_data': trend_data,
        }

    @classmethod
    def get_dashboard_summary(cls, target_date=None):
        """获取仪表板评分汇总"""
        from django.utils import timezone
        from .models import HealthScoreRecord

        if target_date is None:
            target_date = timezone.now().date()

        pens = cls._get_active_pens()
        pen_ids = list(pens.values_list('id', flat=True))

        records = HealthScoreRecord.objects.filter(
            score_date=target_date,
            pen_id__in=pen_ids
        ).select_related('pen')

        if not records.exists():
            cls.calculate_and_save_daily_scores(target_date)
            records = HealthScoreRecord.objects.filter(
                score_date=target_date,
                pen_id__in=pen_ids
            ).select_related('pen')

        total_pens = records.count()
        if total_pens == 0:
            return {
                'date': target_date.isoformat(),
                'total_pens': 0,
                'average_score': 0,
                'risk_distribution': {},
                'top_issues': [],
            }

        avg_score = round(sum(r.total_score for r in records) / total_pens, 2)

        from collections import defaultdict
        by_risk = defaultdict(int)
        for r in records:
            by_risk[r.get_risk_level_display()] += 1

        low_score_pens = records.order_by('total_score')[:5]
        top_issues = []
        for r in low_score_pens:
            top_issues.append({
                'pen_id': r.pen_id,
                'pen_code': r.pen.code,
                'pen_name': r.pen.name,
                'score': r.total_score,
                'risk_level': r.risk_level,
                'risk_level_display': r.get_risk_level_display(),
                'deduction': r.deduction,
                'abnormal_count': r.inspection_abnormal_count + r.open_incidents_count,
            })

        return {
            'date': target_date.isoformat(),
            'total_pens': total_pens,
            'average_score': avg_score,
            'risk_distribution': dict(by_risk),
            'top_issues': top_issues,
        }


health_score_service = HealthScoreService()
