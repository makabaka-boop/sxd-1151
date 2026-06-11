"""
Django admin 配置
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Pen, InspectionItem, InspectionRecord, InspectionItemValue,
    FeedingRecord, CleaningRecord, Incident, IncidentUpdate
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'real_name', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'real_name')
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('个人信息', {'fields': ('real_name', 'role', 'phone')}),
        ('权限', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('重要日期', {'fields': ('last_login', 'created_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'real_name', 'role', 'password1', 'password2'),
        }),
    )
    readonly_fields = ('created_at', 'last_login')


@admin.register(Pen)
class PenAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'livestock_type', 'current_count', 'capacity', 'is_active')
    list_filter = ('livestock_type', 'is_active')
    search_fields = ('code', 'name', 'location')
    ordering = ('code',)


@admin.register(InspectionItem)
class InspectionItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'value_type', 'unit', 'min_value', 'max_value', 'sort_order', 'is_active')
    list_filter = ('value_type', 'unit', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('sort_order', 'code')


class InspectionItemValueInline(admin.TabularInline):
    model = InspectionItemValue
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(InspectionRecord)
class InspectionRecordAdmin(admin.ModelAdmin):
    list_display = ('pen', 'inspector', 'inspection_time', 'created_at')
    list_filter = ('pen', 'inspector', 'inspection_time')
    search_fields = ('pen__code', 'pen__name', 'inspector__real_name')
    date_hierarchy = 'inspection_time'
    ordering = ('-inspection_time',)
    inlines = [InspectionItemValueInline]
    readonly_fields = ('created_at',)


@admin.register(FeedingRecord)
class FeedingRecordAdmin(admin.ModelAdmin):
    list_display = ('pen', 'feeder', 'feed_type', 'feed_amount', 'feeding_time')
    list_filter = ('pen', 'feeder', 'feed_type', 'feeding_time')
    search_fields = ('pen__code', 'pen__name', 'feed_type')
    date_hierarchy = 'feeding_time'
    ordering = ('-feeding_time',)
    readonly_fields = ('created_at',)


@admin.register(CleaningRecord)
class CleaningRecordAdmin(admin.ModelAdmin):
    list_display = ('pen', 'cleaner', 'cleaning_type', 'cleaning_time', 'duration_minutes')
    list_filter = ('pen', 'cleaner', 'cleaning_type', 'cleaning_time')
    search_fields = ('pen__code', 'pen__name')
    date_hierarchy = 'cleaning_time'
    ordering = ('-cleaning_time',)
    readonly_fields = ('created_at',)


class IncidentUpdateInline(admin.TabularInline):
    model = IncidentUpdate
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('pen', 'title', 'severity', 'status', 'reporter', 'incident_time', 'resolved_time')
    list_filter = ('pen', 'severity', 'status', 'incident_time')
    search_fields = ('title', 'description', 'pen__code', 'pen__name')
    date_hierarchy = 'incident_time'
    ordering = ('-incident_time',)
    inlines = [IncidentUpdateInline]
    readonly_fields = ('created_at', 'updated_at')
