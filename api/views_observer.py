"""
观察员查询接口
权限：所有登录用户可访问，无写入权限
包含：历史快照查询、时间轴回滚、差异对比、趋势分析、日报导出
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.utils import timezone
from datetime import datetime, timedelta, date
from .models import Pen
from .serializers import PenSerializer
from .permissions import CanViewReports, CanExportReports
from .services import snapshot_service
from .export_service import export_service


class SnapshotViewSet(viewsets.GenericViewSet):
    """快照查询接口 - 核心的时间轴回滚与快照功能"""
    permission_classes = [IsAuthenticated, CanViewReports]
    queryset = Pen.objects.none()

    def list(self, request, *args, **kwargs):
        """默认返回今日快照
        """
        return self.today(request)

    @action(detail=False, methods=['get'])
    def daily(self, request):
        """
        获取指定日期的栏区状态快照
        参数:
            date: 日期 (YYYY-MM-DD)，默认今日
            pen_id: 栏区ID，可选，不填则返回所有栏区
            with_comparison: 是否返回与前一日的对比 (true/false)
        """
        target_date = request.query_params.get('date', timezone.now().date().isoformat())
        pen_id = request.query_params.get('pen_id')
        with_comparison = request.query_params.get('with_comparison', 'false').lower() == 'true'

        try:
            if isinstance(target_date, str):
                target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
            else:
                target_date_obj = target_date
        except ValueError:
            return Response(
                {'error': '日期格式错误，请使用 YYYY-MM-DD 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if pen_id:
            try:
                pen_id = int(pen_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'pen_id 必须是整数'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        snapshot = snapshot_service.calculate_daily_snapshot(target_date_obj, pen_id)

        result = {
            'snapshot': snapshot,
            'generated_at': timezone.now().isoformat()
        }

        if with_comparison:
            prev_date = target_date_obj - timedelta(days=1)
            prev_snapshot = snapshot_service.calculate_daily_snapshot(prev_date, pen_id)
            comparison = snapshot_service.compare_snapshots(prev_date, target_date_obj, pen_id)
            result['previous_snapshot'] = prev_snapshot
            result['comparison'] = comparison

        return Response(result)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """获取今日快照（快捷方式）"""
        target_date = timezone.now().date()
        pen_id = request.query_params.get('pen_id')
        snapshot = snapshot_service.calculate_daily_snapshot(target_date, pen_id)
        return Response({
            'snapshot': snapshot,
            'generated_at': timezone.now().isoformat()
        })

    @action(detail=False, methods=['get'])
    def compare(self, request):
        """
        对比两个日期的快照差异
        参数:
            date1: 第一个日期 (YYYY-MM-DD)
            date2: 第二个日期 (YYYY-MM-DD)
            pen_id: 栏区ID，可选
        """
        date1 = request.query_params.get('date1')
        date2 = request.query_params.get('date2')
        pen_id = request.query_params.get('pen_id')

        if not date1 or not date2:
            return Response(
                {'error': '必须提供 date1 和 date2 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            date1_obj = datetime.strptime(date1, '%Y-%m-%d').date()
            date2_obj = datetime.strptime(date2, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': '日期格式错误，请使用 YYYY-MM-DD 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if pen_id:
            try:
                pen_id = int(pen_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'pen_id 必须是整数'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        comparison = snapshot_service.compare_snapshots(date1_obj, date2_obj, pen_id)
        return Response(comparison)

    @action(detail=False, methods=['get'])
    def trend(self, request):
        """
        获取指定时间范围内的趋势数据
        参数:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)，默认今日
            pen_id: 栏区ID，可选
            metric: 指标，可选值:
                completion_rate (巡检完成率, 默认)
                open_incidents (待处理事件数)
                abnormal_count (异常总数)
                feeding_count (喂养次数)
                cleaning_count (清洁次数)
        """
        end_date = request.query_params.get('end_date', timezone.now().date().isoformat())
        start_date = request.query_params.get('start_date')
        pen_id = request.query_params.get('pen_id')
        metric = request.query_params.get('metric', 'completion_rate')

        if not start_date:
            return Response(
                {'error': '必须提供 start_date 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': '日期格式错误，请使用 YYYY-MM-DD 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_date_obj > end_date_obj:
            return Response(
                {'error': 'start_date 不能晚于 end_date'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if pen_id:
            try:
                pen_id = int(pen_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'pen_id 必须是整数'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        valid_metrics = ['completion_rate', 'open_incidents', 'abnormal_count', 'feeding_count', 'cleaning_count']
        if metric not in valid_metrics:
            return Response(
                {'error': f'无效的 metric 参数，可选值: {valid_metrics}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        trend_data = snapshot_service.get_trend_data(start_date_obj, end_date_obj, pen_id, metric)
        return Response(trend_data)

    @action(detail=False, methods=['get'])
    def weekly_trend(self, request):
        """获取过去7天的趋势（快捷方式）"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=6)
        pen_id = request.query_params.get('pen_id')
        metric = request.query_params.get('metric', 'completion_rate')

        if pen_id:
            try:
                pen_id = int(pen_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'pen_id 必须是整数'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        trend_data = snapshot_service.get_trend_data(start_date, end_date, pen_id, metric)
        return Response(trend_data)

    @action(detail=False, methods=['get'])
    def incident_timeline(self, request):
        """
        获取异常事件的完整时间线
        参数:
            incident_id: 事件ID
        """
        incident_id = request.query_params.get('incident_id')
        if not incident_id:
            return Response(
                {'error': '必须提供 incident_id 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            incident_id = int(incident_id)
        except (ValueError, TypeError):
            return Response(
                {'error': 'incident_id 必须是整数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        timeline_data = snapshot_service.get_incident_timeline(incident_id)
        if timeline_data is None:
            return Response(
                {'error': '事件不存在'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(timeline_data)

    @action(detail=False, methods=['get'])
    def rollback(self, request):
        """
        时间轴回滚 - 获取指定历史日期的完整状态
        与 daily 类似，但会同时返回与当前状态的对比
        参数:
            date: 历史日期 (YYYY-MM-DD)
            pen_id: 栏区ID，可选
        """
        target_date = request.query_params.get('date')
        pen_id = request.query_params.get('pen_id')

        if not target_date:
            return Response(
                {'error': '必须提供 date 参数'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': '日期格式错误，请使用 YYYY-MM-DD 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if pen_id:
            try:
                pen_id = int(pen_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'pen_id 必须是整数'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        today = timezone.now().date()
        historical_snapshot = snapshot_service.calculate_daily_snapshot(target_date_obj, pen_id)
        current_snapshot = snapshot_service.calculate_daily_snapshot(today, pen_id)
        comparison = snapshot_service.compare_snapshots(target_date_obj, today, pen_id)

        return Response({
            'historical_date': target_date_obj.isoformat(),
            'current_date': today.isoformat(),
            'historical_snapshot': historical_snapshot,
            'current_snapshot': current_snapshot,
            'comparison': comparison
        })


class ReportViewSet(viewsets.GenericViewSet):
    """报表导出接口"""
    permission_classes = [IsAuthenticated, CanExportReports]
    queryset = Pen.objects.none()

    def list(self, request, *args, **kwargs):
        """默认导出今日Excel日报
        """
        return self.daily(request)

    @action(detail=False, methods=['get'])
    def daily(self, request):
        """
        导出日报
        参数:
            date: 日期 (YYYY-MM-DD)，默认今日
            file_format: 格式，可选 excel 或 pdf，默认 excel
            pen_id: 栏区ID，可选
        """
        target_date = request.query_params.get('date', timezone.now().date().isoformat())
        format_type = request.query_params.get('file_format', 'excel').lower()
        pen_id = request.query_params.get('pen_id')

        try:
            target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': '日期格式错误，请使用 YYYY-MM-DD 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if format_type not in ['excel', 'pdf']:
            return Response(
                {'error': '格式只能是 excel 或 pdf'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if pen_id:
            try:
                pen_id = int(pen_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'pen_id 必须是整数'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return export_service.export_daily_report(target_date_obj, format_type, pen_id)

    @action(detail=False, methods=['get'])
    def weekly(self, request):
        """
        导出周报（汇总过去7天的数据）
        参数:
            end_date: 结束日期 (YYYY-MM-DD)，默认今日
            file_format: 格式，可选 excel 或 pdf，默认 excel
            pen_id: 栏区ID，可选
        """
        end_date = request.query_params.get('end_date', timezone.now().date().isoformat())
        format_type = request.query_params.get('file_format', 'excel').lower()
        pen_id = request.query_params.get('pen_id')

        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': '日期格式错误，请使用 YYYY-MM-DD 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if format_type not in ['excel', 'pdf']:
            return Response(
                {'error': '格式只能是 excel 或 pdf'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if pen_id:
            try:
                pen_id = int(pen_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'pen_id 必须是整数'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        from .export_service import export_service
        return export_service.export_weekly_report(end_date_obj, format_type, pen_id)

    @action(detail=False, methods=['get'])
    def available_dates(self, request):
        """
        获取有数据的日期列表
        参数:
            start_date: 开始日期，可选
            end_date: 结束日期，可选
        """
        from .models import InspectionRecord, FeedingRecord, CleaningRecord, Incident
        from django.db.models import DateField
        from django.db.models.functions import Cast

        end_date = request.query_params.get('end_date', timezone.now().date().isoformat())
        start_date = request.query_params.get('start_date', (timezone.now().date() - timedelta(days=30)).isoformat())

        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': '日期格式错误，请使用 YYYY-MM-DD 格式'},
                status=status.HTTP_400_BAD_REQUEST
            )

        dates = set()

        models_to_check = [
            (InspectionRecord, 'inspection_time'),
            (FeedingRecord, 'feeding_time'),
            (CleaningRecord, 'cleaning_time'),
            (Incident, 'incident_time'),
        ]

        for model, field_name in models_to_check:
            queryset = model.objects.filter(
                **{f'{field_name}__date__gte': start_date_obj, f'{field_name}__date__lte': end_date_obj}
            ).annotate(
                date=Cast(field_name, output_field=DateField())
            ).values_list('date', flat=True).distinct()

            for d in queryset:
                if isinstance(d, date):
                    dates.add(d.isoformat())

        return Response({
            'start_date': start_date,
            'end_date': end_date,
            'available_dates': sorted(list(dates), reverse=True),
            'count': len(dates)
        })


class DashboardView(APIView):
    """仪表板数据接口 - 首页概览"""
    permission_classes = [IsAuthenticated, CanViewReports]

    def get(self, request):
        """获取仪表板概览数据"""
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)

        today_snapshot = snapshot_service.calculate_daily_snapshot(today)
        yesterday_snapshot = snapshot_service.calculate_daily_snapshot(yesterday)

        week_start = today - timedelta(days=6)
        week_trend = snapshot_service.get_trend_data(week_start, today, None, 'completion_rate')

        from .models import Incident
        open_incidents = Incident.objects.filter(status__in=['OPEN', 'IN_PROGRESS']).count()
        high_priority = Incident.objects.filter(
            status__in=['OPEN', 'IN_PROGRESS'],
            severity__in=['HIGH', 'CRITICAL']
        ).count()

        return Response({
            'today': today.isoformat(),
            'today_snapshot': today_snapshot,
            'yesterday_snapshot': yesterday_snapshot,
            'weekly_trend': week_trend,
            'open_incidents': open_incidents,
            'high_priority_incidents': high_priority,
        })
