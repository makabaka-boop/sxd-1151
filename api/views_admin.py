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
from .models import Pen, InspectionItem
from .serializers import (
    UserSerializer, UserCreateSerializer,
    PenSerializer, InspectionItemSerializer
)
from .permissions import IsAdmin, IsAdminOrReadOnly

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
