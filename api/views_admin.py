"""
管理员配置接口
权限：仅管理员可访问（写入）
包含：用户管理、栏区CRUD、巡检项CRUD
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from .models import (
    Pen, InspectionItem, HealthScoreConfig,
    HealthScoreInspectionItem, HealthScoreRiskThreshold
)
from .serializers import (
    UserSerializer, UserCreateSerializer,
    PenSerializer, InspectionItemSerializer,
    HealthScoreConfigSerializer, HealthScoreInspectionItemSerializer,
    HealthScoreRiskThresholdSerializer
)
from .permissions import IsAdmin, IsAdminOrReadOnly
from .services import health_score_service

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """用户管理 - 仅管理员可访问"""
    queryset = User.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated, IsAdmin]
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'real_name', 'phone']

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    @action(detail=False, methods=['get'])
    def current(self, request):
        """获取当前登录用户信息"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class PenViewSet(viewsets.ModelViewSet):
    """栏区管理 - 管理员可写，其他只读"""
    queryset = Pen.objects.all().order_by('code')
    serializer_class = PenSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    filterset_fields = ['livestock_type', 'is_active']
    search_fields = ['code', 'name', 'location']

    @action(detail=False, methods=['get'])
    def active(self, request):
        """获取所有活跃的栏区"""
        queryset = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class InspectionItemViewSet(viewsets.ModelViewSet):
    """巡检项管理 - 管理员可写，其他只读"""
    queryset = InspectionItem.objects.all().order_by('sort_order', 'code')
    serializer_class = InspectionItemSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    filterset_fields = ['value_type', 'unit', 'is_active']
    search_fields = ['code', 'name', 'description']

    @action(detail=False, methods=['get'])
    def active(self, request):
        """获取所有活跃的巡检项"""
        queryset = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def batch_update_order(self, request):
        """批量更新排序"""
        items = request.data.get('items', [])
        for item_data in items:
            item_id = item_data.get('id')
            sort_order = item_data.get('sort_order')
            if item_id and sort_order is not None:
                InspectionItem.objects.filter(id=item_id).update(sort_order=sort_order)
        return Response({'message': '排序更新成功'})


class HealthScoreConfigViewSet(viewsets.ModelViewSet):
    """健康评分维度配置 - 仅管理员可写"""
    queryset = HealthScoreConfig.objects.all().order_by('sort_order', 'dimension_key')
    serializer_class = HealthScoreConfigSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    filterset_fields = ['dimension_key', 'is_enabled']

    @action(detail=False, methods=['post'])
    def batch_update_weights(self, request):
        """批量更新权重和排序"""
        configs = request.data.get('configs', [])
        for config_data in configs:
            config_id = config_data.get('id')
            weight = config_data.get('weight')
            sort_order = config_data.get('sort_order')
            is_enabled = config_data.get('is_enabled')
            if config_id:
                update_data = {}
                if weight is not None:
                    update_data['weight'] = weight
                if sort_order is not None:
                    update_data['sort_order'] = sort_order
                if is_enabled is not None:
                    update_data['is_enabled'] = is_enabled
                if update_data:
                    HealthScoreConfig.objects.filter(id=config_id).update(**update_data)
        return Response({'message': '配置更新成功'})

    @action(detail=False, methods=['post'])
    def initialize_defaults(self, request):
        """初始化默认配置"""
        health_score_service.initialize_default_configs()
        return Response({'message': '默认配置已初始化'})


class HealthScoreInspectionItemViewSet(viewsets.ModelViewSet):
    """评分巡检项配置 - 管理员配置哪些巡检项参与评分"""
    queryset = HealthScoreInspectionItem.objects.all().select_related(
        'inspection_item'
    ).order_by('inspection_item__sort_order')
    serializer_class = HealthScoreInspectionItemSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    filterset_fields = ['inspection_item_id', 'is_enabled']

    @action(detail=False, methods=['post'])
    def batch_update(self, request):
        """批量更新巡检项评分配置"""
        items = request.data.get('items', [])
        for item_data in items:
            item_id = item_data.get('id')
            penalty = item_data.get('penalty_per_abnormal')
            is_enabled = item_data.get('is_enabled')
            if item_id:
                update_data = {}
                if penalty is not None:
                    update_data['penalty_per_abnormal'] = penalty
                if is_enabled is not None:
                    update_data['is_enabled'] = is_enabled
                if update_data:
                    HealthScoreInspectionItem.objects.filter(id=item_id).update(**update_data)
        return Response({'message': '配置更新成功'})


class HealthScoreRiskThresholdViewSet(viewsets.ModelViewSet):
    """风险等级阈值配置 - 仅管理员可写"""
    queryset = HealthScoreRiskThreshold.objects.all().order_by('-min_score')
    serializer_class = HealthScoreRiskThresholdSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    filterset_fields = ['risk_level']
