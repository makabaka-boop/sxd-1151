"""
API 路由配置
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views_admin import UserViewSet, PenViewSet, InspectionItemViewSet
from .views_field import (
    InspectionRecordViewSet, FeedingRecordViewSet,
    CleaningRecordViewSet, IncidentViewSet
)
from .views_observer import SnapshotViewSet, ReportViewSet, DashboardView

router = DefaultRouter()

router.register(r'users', UserViewSet, basename='user')
router.register(r'pens', PenViewSet, basename='pen')
router.register(r'inspection-items', InspectionItemViewSet, basename='inspectionitem')
router.register(r'inspection-records', InspectionRecordViewSet, basename='inspectionrecord')
router.register(r'feeding-records', FeedingRecordViewSet, basename='feedingrecord')
router.register(r'cleaning-records', CleaningRecordViewSet, basename='cleaningrecord')
router.register(r'incidents', IncidentViewSet, basename='incident')

urlpatterns = [
    path('snapshots/', SnapshotViewSet.as_view({'get': 'list'}), name='snapshot-list'),
    path('snapshots/daily/', SnapshotViewSet.as_view({'get': 'daily'}), name='snapshot-daily'),
    path('snapshots/today/', SnapshotViewSet.as_view({'get': 'today'}), name='snapshot-today'),
    path('snapshots/compare/', SnapshotViewSet.as_view({'get': 'compare'}), name='snapshot-compare'),
    path('snapshots/trend/', SnapshotViewSet.as_view({'get': 'trend'}), name='snapshot-trend'),
    path('snapshots/weekly-trend/', SnapshotViewSet.as_view({'get': 'weekly_trend'}), name='snapshot-weekly-trend'),
    path('snapshots/incident-timeline/', SnapshotViewSet.as_view({'get': 'incident_timeline'}), name='snapshot-incident-timeline'),
    path('snapshots/rollback/', SnapshotViewSet.as_view({'get': 'rollback'}), name='snapshot-rollback'),
    path('reports/', ReportViewSet.as_view({'get': 'list'}), name='report-list'),
    path('reports/daily/', ReportViewSet.as_view({'get': 'daily'}), name='report-daily'),
    path('reports/weekly/', ReportViewSet.as_view({'get': 'weekly'}), name='report-weekly'),
    path('reports/available-dates/', ReportViewSet.as_view({'get': 'available_dates'}), name='report-available-dates'),
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
]
