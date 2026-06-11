"""
API 路由配置
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views_admin import (
    UserViewSet, PenViewSet, InspectionItemViewSet,
    HealthScoreConfigViewSet, HealthScoreInspectionItemViewSet,
    HealthScoreRiskThresholdViewSet
)
from .views_field import (
    InspectionRecordViewSet, FeedingRecordViewSet,
    CleaningRecordViewSet, IncidentViewSet
)
from .views_observer import (
    SnapshotViewSet, ReportViewSet, DashboardView,
    HealthScoreViewSet, HealthScoreDetailViewSet
)

router = DefaultRouter()

router.register(r'users', UserViewSet, basename='user')
router.register(r'pens', PenViewSet, basename='pen')
router.register(r'inspection-items', InspectionItemViewSet, basename='inspectionitem')
router.register(r'inspection-records', InspectionRecordViewSet, basename='inspectionrecord')
router.register(r'feeding-records', FeedingRecordViewSet, basename='feedingrecord')
router.register(r'cleaning-records', CleaningRecordViewSet, basename='cleaningrecord')
router.register(r'incidents', IncidentViewSet, basename='incident')
router.register(r'health-score-configs', HealthScoreConfigViewSet, basename='healthscoreconfig')
router.register(r'health-score-inspection-items', HealthScoreInspectionItemViewSet, basename='healthscoreinspectionitem')
router.register(r'health-score-risk-thresholds', HealthScoreRiskThresholdViewSet, basename='healthscoreriskthreshold')

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
    path('health-scores/', HealthScoreViewSet.as_view({'get': 'list'}), name='healthscore-list'),
    path('health-scores/today/', HealthScoreViewSet.as_view({'get': 'today'}), name='healthscore-today'),
    path('health-scores/daily/', HealthScoreViewSet.as_view({'get': 'daily'}), name='healthscore-daily'),
    path('health-scores/trend/', HealthScoreViewSet.as_view({'get': 'trend'}), name='healthscore-trend'),
    path('health-scores/weekly-trend/', HealthScoreViewSet.as_view({'get': 'weekly_trend'}), name='healthscore-weekly-trend'),
    path('health-scores/dashboard-summary/', HealthScoreViewSet.as_view({'get': 'dashboard_summary'}), name='healthscore-dashboard-summary'),
    path('health-scores/recalculate/', HealthScoreViewSet.as_view({'post': 'recalculate'}), name='healthscore-recalculate'),
    path('health-scores/<int:pk>/details/', HealthScoreViewSet.as_view({'get': 'details'}), name='healthscore-details'),
    path('health-scores/<int:pk>/manual-adjust/', HealthScoreViewSet.as_view({'post': 'manual_adjust'}), name='healthscore-manual-adjust'),
    path('health-score-details/', HealthScoreDetailViewSet.as_view({'get': 'list'}), name='healthscoredetail-list'),
    path('health-score-details/<int:pk>/update-rectification/', HealthScoreDetailViewSet.as_view({'post': 'update_rectification'}), name='healthscoredetail-update-rectification'),
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
]
