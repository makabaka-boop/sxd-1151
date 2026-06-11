"""
自定义权限类 - 基于用户角色的三级权限系统
"""
from rest_framework import permissions
from .models import User


class IsAdmin(permissions.BasePermission):
    """仅管理员可访问"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.ADMIN)


class IsFieldWorker(permissions.BasePermission):
    """仅现场人员可访问"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.FIELD_WORKER)


class IsObserver(permissions.BasePermission):
    """仅观察员可访问"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.OBSERVER)


class IsAdminOrFieldWorker(permissions.BasePermission):
    """管理员或现场人员可访问（有写入权限）"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in [User.Role.ADMIN, User.Role.FIELD_WORKER]


class IsAdminOrReadOnly(permissions.BasePermission):
    """管理员可写，其他只读"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role == User.Role.ADMIN


class CanSubmitRecords(permissions.BasePermission):
    """可提交记录：管理员和现场人员"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role in [User.Role.ADMIN, User.Role.FIELD_WORKER]


class CanViewReports(permissions.BasePermission):
    """可查看报表：所有登录用户"""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class CanExportReports(permissions.BasePermission):
    """可导出报表：管理员和观察员"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in [User.Role.ADMIN, User.Role.OBSERVER]
