"""
现场人员接口
权限：管理员和现场人员可写入，观察员只读
包含：巡检记录提交、喂养记录、清洁记录、异常事件上报和处理
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import (
    InspectionRecord, FeedingRecord, CleaningRecord, Incident
)
from .serializers import (
    InspectionRecordSerializer, InspectionRecordCreateSerializer,
    FeedingRecordSerializer, FeedingRecordCreateSerializer,
    CleaningRecordSerializer, CleaningRecordCreateSerializer,
    IncidentSerializer, IncidentCreateSerializer, IncidentStatusUpdateSerializer
)
from .permissions import CanSubmitRecords, IsAdminOrFieldWorker


class InspectionRecordViewSet(viewsets.ModelViewSet):
    """巡检记录管理"""
    queryset = InspectionRecord.objects.all().select_related(
        'pen', 'inspector'
    ).prefetch_related('item_values__inspection_item').order_by('-inspection_time')
    permission_classes = [IsAuthenticated, CanSubmitRecords]
    filterset_fields = ['pen_id', 'inspector_id']
    search_fields = ['pen__code', 'pen__name', 'inspector__real_name', 'remarks']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return InspectionRecordCreateSerializer
        return InspectionRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        has_abnormal = self.request.query_params.get('has_abnormal')

        if date_from:
            start_dt = datetime.strptime(date_from, '%Y-%m-%d')
            queryset = queryset.filter(inspection_time__gte=start_dt)
        if date_to:
            end_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            queryset = queryset.filter(inspection_time__lt=end_dt)

        if has_abnormal == 'true':
            queryset = queryset.filter(item_values__is_abnormal=True).distinct()
        elif has_abnormal == 'false':
            queryset = queryset.exclude(item_values__is_abnormal=True).distinct()

        return queryset

    def create(self, request, *args, **kwargs):
        """提交巡检记录"""
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """获取今日巡检记录"""
        today = timezone.now().date()
        start_dt = datetime.combine(today, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        queryset = self.get_queryset().filter(
            inspection_time__gte=start_dt,
            inspection_time__lt=end_dt
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_records(self, request):
        """获取当前用户提交的巡检记录"""
        queryset = self.get_queryset().filter(inspector=request.user)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class FeedingRecordViewSet(viewsets.ModelViewSet):
    """喂养记录管理"""
    queryset = FeedingRecord.objects.all().select_related(
        'pen', 'feeder'
    ).order_by('-feeding_time')
    permission_classes = [IsAuthenticated, CanSubmitRecords]
    filterset_fields = ['pen_id', 'feeder_id', 'feed_type']
    search_fields = ['pen__code', 'pen__name', 'feed_type', 'feeder__real_name']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FeedingRecordCreateSerializer
        return FeedingRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if date_from:
            start_dt = datetime.strptime(date_from, '%Y-%m-%d')
            queryset = queryset.filter(feeding_time__gte=start_dt)
        if date_to:
            end_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            queryset = queryset.filter(feeding_time__lt=end_dt)

        return queryset

    def create(self, request, *args, **kwargs):
        """提交喂养记录"""
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """获取今日喂养记录"""
        today = timezone.now().date()
        start_dt = datetime.combine(today, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        queryset = self.get_queryset().filter(
            feeding_time__gte=start_dt,
            feeding_time__lt=end_dt
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """喂养记录汇总"""
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to', timezone.now().date().isoformat())
        pen_id = request.query_params.get('pen_id')

        queryset = self.get_queryset()
        if date_from:
            queryset = queryset.filter(feeding_time__gte=datetime.strptime(date_from, '%Y-%m-%d'))
        queryset = queryset.filter(feeding_time__lt=datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        if pen_id:
            queryset = queryset.filter(pen_id=pen_id)

        from django.db.models import Sum, Count
        summary = queryset.values('pen_id', 'pen__code', 'pen__name').annotate(
            total_amount=Sum('feed_amount'),
            record_count=Count('id'),
            feed_types=Count('feed_type', distinct=True)
        )

        return Response(list(summary))


class CleaningRecordViewSet(viewsets.ModelViewSet):
    """清洁记录管理"""
    queryset = CleaningRecord.objects.all().select_related(
        'pen', 'cleaner'
    ).order_by('-cleaning_time')
    permission_classes = [IsAuthenticated, CanSubmitRecords]
    filterset_fields = ['pen_id', 'cleaner_id', 'cleaning_type']
    search_fields = ['pen__code', 'pen__name', 'cleaner__real_name', 'disinfectant_used']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CleaningRecordCreateSerializer
        return CleaningRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if date_from:
            start_dt = datetime.strptime(date_from, '%Y-%m-%d')
            queryset = queryset.filter(cleaning_time__gte=start_dt)
        if date_to:
            end_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            queryset = queryset.filter(cleaning_time__lt=end_dt)

        return queryset

    def create(self, request, *args, **kwargs):
        """提交清洁记录"""
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """获取今日清洁记录"""
        today = timezone.now().date()
        start_dt = datetime.combine(today, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        queryset = self.get_queryset().filter(
            cleaning_time__gte=start_dt,
            cleaning_time__lt=end_dt
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class IncidentViewSet(viewsets.ModelViewSet):
    """异常事件管理"""
    queryset = Incident.objects.all().select_related(
        'pen', 'reporter', 'handler'
    ).prefetch_related('updates__operator').order_by('-incident_time')
    permission_classes = [IsAuthenticated, CanSubmitRecords]
    filterset_fields = ['pen_id', 'reporter_id', 'handler_id', 'severity', 'status']
    search_fields = ['title', 'description', 'pen__code', 'pen__name', 'reporter__real_name']

    def get_serializer_class(self):
        if self.action in ['create']:
            return IncidentCreateSerializer
        if self.action in ['update', 'partial_update']:
            return IncidentStatusUpdateSerializer
        return IncidentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if date_from:
            start_dt = datetime.strptime(date_from, '%Y-%m-%d')
            queryset = queryset.filter(incident_time__gte=start_dt)
        if date_to:
            end_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            queryset = queryset.filter(incident_time__lt=end_dt)

        return queryset

    def create(self, request, *args, **kwargs):
        """上报异常事件"""
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """更新事件状态（处理事件）"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def open(self, request):
        """获取所有待处理和处理中的事件"""
        queryset = self.get_queryset().filter(status__in=['OPEN', 'IN_PROGRESS'])
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_reported(self, request):
        """获取我上报的事件"""
        queryset = self.get_queryset().filter(reporter=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_handled(self, request):
        """获取我处理的事件"""
        queryset = self.get_queryset().filter(handler=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """更新事件状态"""
        instance = self.get_object()
        serializer = IncidentStatusUpdateSerializer(
            instance, data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def timeline(self, request, pk=None):
        """获取事件完整时间线"""
        from .services import snapshot_service
        timeline_data = snapshot_service.get_incident_timeline(pk)
        if timeline_data is None:
            return Response({'error': '事件不存在'}, status=status.HTTP_404_NOT_FOUND)
        return Response(timeline_data)
