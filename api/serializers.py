"""
序列化器定义
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    Pen, InspectionItem, InspectionRecord, InspectionItemValue,
    FeedingRecord, CleaningRecord, Incident, IncidentUpdate
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'real_name', 'role', 'role_display', 'phone', 'is_active', 'created_at']
        read_only_fields = ['created_at']


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['username', 'real_name', 'role', 'phone', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class PenSerializer(serializers.ModelSerializer):
    livestock_type_display = serializers.CharField(source='get_livestock_type_display', read_only=True)

    class Meta:
        model = Pen
        fields = [
            'id', 'code', 'name', 'location', 'livestock_type', 'livestock_type_display',
            'capacity', 'current_count', 'description', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class InspectionItemSerializer(serializers.ModelSerializer):
    value_type_display = serializers.CharField(source='get_value_type_display', read_only=True)
    unit_display = serializers.SerializerMethodField()

    class Meta:
        model = InspectionItem
        fields = [
            'id', 'code', 'name', 'value_type', 'value_type_display',
            'unit', 'unit_display', 'custom_unit', 'min_value', 'max_value',
            'choice_options', 'description', 'sort_order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_unit_display(self, obj):
        if obj.unit == 'CUSTOM':
            return obj.custom_unit
        return obj.get_unit_display()


class InspectionItemValueSerializer(serializers.ModelSerializer):
    inspection_item_code = serializers.CharField(source='inspection_item.code', read_only=True)
    inspection_item_name = serializers.CharField(source='inspection_item.name', read_only=True)
    display_value = serializers.CharField(read_only=True)

    class Meta:
        model = InspectionItemValue
        fields = [
            'id', 'inspection_item_id', 'inspection_item_code', 'inspection_item_name',
            'numeric_value', 'boolean_value', 'text_value', 'is_abnormal', 'display_value'
        ]


class InspectionItemValueCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionItemValue
        fields = ['inspection_item_id', 'numeric_value', 'boolean_value', 'text_value']

    def validate(self, attrs):
        inspection_item = InspectionItem.objects.get(id=attrs['inspection_item_id'])
        value_type = inspection_item.value_type

        if value_type == InspectionItem.ValueType.NUMERIC and attrs.get('numeric_value') is None:
            raise serializers.ValidationError(f'巡检项 {inspection_item.name} 需要数值')
        if value_type == InspectionItem.ValueType.BOOLEAN and attrs.get('boolean_value') is None:
            raise serializers.ValidationError(f'巡检项 {inspection_item.name} 需要布尔值')
        if value_type in [InspectionItem.ValueType.TEXT, InspectionItem.ValueType.CHOICE] and not attrs.get('text_value'):
            raise serializers.ValidationError(f'巡检项 {inspection_item.name} 需要文本值')

        return attrs


class InspectionRecordSerializer(serializers.ModelSerializer):
    pen_code = serializers.CharField(source='pen.code', read_only=True)
    pen_name = serializers.CharField(source='pen.name', read_only=True)
    inspector_name = serializers.CharField(source='inspector.real_name', read_only=True)
    item_values = InspectionItemValueSerializer(many=True, read_only=True)

    class Meta:
        model = InspectionRecord
        fields = [
            'id', 'pen_id', 'pen_code', 'pen_name', 'inspector_id', 'inspector_name',
            'inspection_time', 'remarks', 'item_values', 'created_at'
        ]
        read_only_fields = ['created_at', 'inspector_id']


class InspectionRecordCreateSerializer(serializers.ModelSerializer):
    item_values = InspectionItemValueCreateSerializer(many=True, required=True)

    class Meta:
        model = InspectionRecord
        fields = ['pen_id', 'inspection_time', 'remarks', 'item_values']

    def validate_item_values(self, value):
        if not value:
            raise serializers.ValidationError('至少需要填写一个巡检项')

        item_ids = [v['inspection_item_id'] for v in value]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError('存在重复的巡检项')

        return value

    def create(self, validated_data):
        item_values_data = validated_data.pop('item_values')
        validated_data['inspector'] = self.context['request'].user
        record = InspectionRecord.objects.create(**validated_data)

        for item_value_data in item_values_data:
            inspection_item = InspectionItem.objects.get(id=item_value_data['inspection_item_id'])
            is_abnormal = False

            if inspection_item.value_type == InspectionItem.ValueType.NUMERIC:
                is_abnormal = not inspection_item.is_value_normal(item_value_data.get('numeric_value'))

            InspectionItemValue.objects.create(
                record=record,
                inspection_item=inspection_item,
                numeric_value=item_value_data.get('numeric_value'),
                boolean_value=item_value_data.get('boolean_value'),
                text_value=item_value_data.get('text_value', ''),
                is_abnormal=is_abnormal
            )

        return record


class FeedingRecordSerializer(serializers.ModelSerializer):
    pen_code = serializers.CharField(source='pen.code', read_only=True)
    pen_name = serializers.CharField(source='pen.name', read_only=True)
    feeder_name = serializers.CharField(source='feeder.real_name', read_only=True)

    class Meta:
        model = FeedingRecord
        fields = [
            'id', 'pen_id', 'pen_code', 'pen_name', 'feeder_id', 'feeder_name',
            'feed_type', 'feed_amount', 'feeding_time', 'remarks', 'created_at'
        ]
        read_only_fields = ['created_at', 'feeder_id']


class FeedingRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedingRecord
        fields = ['pen_id', 'feed_type', 'feed_amount', 'feeding_time', 'remarks']

    def create(self, validated_data):
        validated_data['feeder'] = self.context['request'].user
        return super().create(validated_data)


class CleaningRecordSerializer(serializers.ModelSerializer):
    pen_code = serializers.CharField(source='pen.code', read_only=True)
    pen_name = serializers.CharField(source='pen.name', read_only=True)
    cleaner_name = serializers.CharField(source='cleaner.real_name', read_only=True)
    cleaning_type_display = serializers.CharField(source='get_cleaning_type_display', read_only=True)

    class Meta:
        model = CleaningRecord
        fields = [
            'id', 'pen_id', 'pen_code', 'pen_name', 'cleaner_id', 'cleaner_name',
            'cleaning_type', 'cleaning_type_display', 'cleaning_time', 'duration_minutes',
            'disinfectant_used', 'remarks', 'created_at'
        ]
        read_only_fields = ['created_at', 'cleaner_id']


class CleaningRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CleaningRecord
        fields = ['pen_id', 'cleaning_type', 'cleaning_time', 'duration_minutes', 'disinfectant_used', 'remarks']

    def create(self, validated_data):
        validated_data['cleaner'] = self.context['request'].user
        return super().create(validated_data)


class IncidentUpdateSerializer(serializers.ModelSerializer):
    operator_name = serializers.CharField(source='operator.real_name', read_only=True)
    old_status_display = serializers.CharField(source='get_old_status_display', read_only=True)
    new_status_display = serializers.CharField(source='get_new_status_display', read_only=True)

    class Meta:
        model = IncidentUpdate
        fields = [
            'id', 'operator_id', 'operator_name', 'old_status', 'old_status_display',
            'new_status', 'new_status_display', 'comment', 'created_at'
        ]
        read_only_fields = ['created_at', 'operator_id', 'old_status']


class IncidentSerializer(serializers.ModelSerializer):
    pen_code = serializers.CharField(source='pen.code', read_only=True)
    pen_name = serializers.CharField(source='pen.name', read_only=True)
    reporter_name = serializers.CharField(source='reporter.real_name', read_only=True)
    handler_name = serializers.CharField(source='handler.real_name', read_only=True, allow_null=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    updates = IncidentUpdateSerializer(many=True, read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = [
            'id', 'pen_id', 'pen_code', 'pen_name', 'reporter_id', 'reporter_name',
            'title', 'description', 'severity', 'severity_display', 'status', 'status_display',
            'incident_time', 'inspection_record_id', 'handler_id', 'handler_name',
            'resolution', 'resolved_time', 'duration', 'updates', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'reporter_id']

    def get_duration(self, obj):
        """获取事件持续时间（小时）"""
        if obj.resolved_time:
            duration = obj.resolved_time - obj.incident_time
            return round(duration.total_seconds() / 3600, 2)
        duration = timezone.now() - obj.incident_time
        return round(duration.total_seconds() / 3600, 2)


class IncidentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = [
            'pen_id', 'title', 'description', 'severity', 'incident_time',
            'inspection_record_id'
        ]

    def create(self, validated_data):
        validated_data['reporter'] = self.context['request'].user
        return super().create(validated_data)


class IncidentStatusUpdateSerializer(serializers.ModelSerializer):
    comment = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Incident
        fields = ['status', 'handler_id', 'resolution', 'comment']

    def update(self, instance, validated_data):
        comment = validated_data.pop('comment', '')
        old_status = instance.status
        new_status = validated_data.get('status', old_status)

        if new_status in [Incident.Status.RESOLVED, Incident.Status.CLOSED]:
            if not validated_data.get('resolution'):
                raise serializers.ValidationError('解决状态必须填写处理方案')
            validated_data['resolved_time'] = timezone.now()

        instance = super().update(instance, validated_data)

        if old_status != new_status:
            IncidentUpdate.objects.create(
                incident=instance,
                operator=self.context['request'].user,
                old_status=old_status,
                new_status=new_status,
                comment=comment
            )

        return instance
