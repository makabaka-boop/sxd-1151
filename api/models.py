"""
数据库模型定义
包含：用户模型（三级权限）、栏区、巡检项、巡检记录、喂养记录、清洁记录、异常事件
"""
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


class UserManager(BaseUserManager):
    """用户管理器"""
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('用户名必须提供')
        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('role', User.Role.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    用户模型 - 三级权限系统
    ADMIN(管理员): 栏区和巡检项配置权限
    FIELD_WORKER(现场人员): 提交日常巡检记录、标记异常事件
    OBSERVER(观察员): 查看历史报表、下载日报，无写入权限
    """
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', '管理员'
        FIELD_WORKER = 'FIELD_WORKER', '现场人员'
        OBSERVER = 'OBSERVER', '观察员'

    username = models.CharField(max_length=50, unique=True, verbose_name='用户名')
    real_name = models.CharField(max_length=50, verbose_name='真实姓名')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OBSERVER, verbose_name='角色')
    phone = models.CharField(max_length=20, blank=True, verbose_name='联系电话')
    is_active = models.BooleanField(default=True, verbose_name='是否激活')
    is_staff = models.BooleanField(default=False, verbose_name='是否可登录后台')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['real_name']

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.real_name} ({self.get_role_display()})'


class Pen(models.Model):
    """
    栏区表 - 养殖场的各个栏区
    """
    code = models.CharField(max_length=50, unique=True, verbose_name='栏区编号')
    name = models.CharField(max_length=100, verbose_name='栏区名称')
    location = models.CharField(max_length=200, blank=True, verbose_name='位置描述')
    livestock_type = models.CharField(max_length=50, verbose_name='养殖类型')  # 如：生猪、奶牛、家禽等
    capacity = models.IntegerField(default=0, verbose_name='容量')
    current_count = models.IntegerField(default=0, verbose_name='当前数量')
    description = models.TextField(blank=True, verbose_name='备注')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '栏区'
        verbose_name_plural = verbose_name
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'


class InspectionItem(models.Model):
    """
    巡检项表 - 定义需要巡检的指标
    如：温度、湿度、饲料剩余量、饮水量、空气质量等
    """
    class ValueType(models.TextChoices):
        NUMERIC = 'NUMERIC', '数值型'
        BOOLEAN = 'BOOLEAN', '布尔型'
        TEXT = 'TEXT', '文本型'
        CHOICE = 'CHOICE', '选择型'

    class Unit(models.TextChoices):
        CELSIUS = '°C', '摄氏度'
        PERCENT = '%', '百分比'
        KG = 'kg', '千克'
        LITER = 'L', '升'
        PPM = 'ppm', '百万分比'
        NONE = '', '无'
        CUSTOM = 'CUSTOM', '自定义'

    code = models.CharField(max_length=50, unique=True, verbose_name='巡检项编码')
    name = models.CharField(max_length=100, verbose_name='巡检项名称')
    value_type = models.CharField(max_length=20, choices=ValueType.choices, default=ValueType.NUMERIC, verbose_name='值类型')
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.NONE, verbose_name='单位')
    custom_unit = models.CharField(max_length=20, blank=True, verbose_name='自定义单位')
    min_value = models.FloatField(null=True, blank=True, verbose_name='正常值下限')
    max_value = models.FloatField(null=True, blank=True, verbose_name='正常值上限')
    choice_options = models.JSONField(default=list, blank=True, verbose_name='选择项列表')
    description = models.TextField(blank=True, verbose_name='巡检说明')
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '巡检项'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'code']

    def __str__(self):
        unit_display = self.custom_unit if self.unit == 'CUSTOM' else self.get_unit_display()
        return f'{self.code} - {self.name} ({unit_display})'

    def is_value_normal(self, value):
        """检查值是否在正常范围内"""
        if self.value_type != self.ValueType.NUMERIC:
            return True
        if value is None:
            return False
        if self.min_value is not None and float(value) < self.min_value:
            return False
        if self.max_value is not None and float(value) > self.max_value:
            return False
        return True


class InspectionRecord(models.Model):
    """
    巡检记录表 - 现场人员提交的巡检记录
    每条记录对应一个栏区在某个时间点的一次巡检，包含多个巡检项值
    """
    pen = models.ForeignKey(Pen, on_delete=models.PROTECT, related_name='inspection_records', verbose_name='栏区')
    inspector = models.ForeignKey(User, on_delete=models.PROTECT, related_name='inspection_records', verbose_name='巡检人')
    inspection_time = models.DateTimeField(default=timezone.now, verbose_name='巡检时间')
    remarks = models.TextField(blank=True, verbose_name='巡检备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '巡检记录'
        verbose_name_plural = verbose_name
        ordering = ['-inspection_time']
        indexes = [
            models.Index(fields=['pen', 'inspection_time']),
            models.Index(fields=['inspection_time']),
        ]

    def __str__(self):
        return f'{self.pen.code} - {self.inspection_time.strftime("%Y-%m-%d %H:%M")}'


class InspectionItemValue(models.Model):
    """
    巡检项值 - 每条巡检记录中各个巡检项的具体值
    """
    record = models.ForeignKey(InspectionRecord, on_delete=models.CASCADE, related_name='item_values', verbose_name='巡检记录')
    inspection_item = models.ForeignKey(InspectionItem, on_delete=models.PROTECT, related_name='values', verbose_name='巡检项')
    numeric_value = models.FloatField(null=True, blank=True, verbose_name='数值')
    boolean_value = models.BooleanField(null=True, blank=True, verbose_name='布尔值')
    text_value = models.TextField(blank=True, verbose_name='文本值')
    is_abnormal = models.BooleanField(default=False, verbose_name='是否异常')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '巡检项值'
        verbose_name_plural = verbose_name
        ordering = ['record', 'inspection_item__sort_order']
        indexes = [
            models.Index(fields=['record', 'inspection_item']),
        ]

    def __str__(self):
        return f'{self.record} - {self.inspection_item.name}'

    def get_display_value(self):
        """获取显示值"""
        if self.inspection_item.value_type == InspectionItem.ValueType.NUMERIC:
            return str(self.numeric_value)
        elif self.inspection_item.value_type == InspectionItem.ValueType.BOOLEAN:
            return '是' if self.boolean_value else '否'
        elif self.inspection_item.value_type == InspectionItem.ValueType.TEXT:
            return self.text_value
        elif self.inspection_item.value_type == InspectionItem.ValueType.CHOICE:
            return self.text_value
        return ''


class FeedingRecord(models.Model):
    """
    喂养记录表
    """
    pen = models.ForeignKey(Pen, on_delete=models.PROTECT, related_name='feeding_records', verbose_name='栏区')
    feeder = models.ForeignKey(User, on_delete=models.PROTECT, related_name='feeding_records', verbose_name='喂养人')
    feed_type = models.CharField(max_length=100, verbose_name='饲料类型')
    feed_amount = models.FloatField(verbose_name='投喂量(kg)')
    feeding_time = models.DateTimeField(default=timezone.now, verbose_name='喂养时间')
    remarks = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '喂养记录'
        verbose_name_plural = verbose_name
        ordering = ['-feeding_time']
        indexes = [
            models.Index(fields=['pen', 'feeding_time']),
            models.Index(fields=['feeding_time']),
        ]

    def __str__(self):
        return f'{self.pen.code} - {self.feed_type} {self.feed_amount}kg'


class CleaningRecord(models.Model):
    """
    清洁记录表
    """
    class CleaningType(models.TextChoices):
        DAILY = 'DAILY', '日常清洁'
        DISINFECTION = 'DISINFECTION', '消毒'
        DEEP_CLEAN = 'DEEP_CLEAN', '深度清洁'
        WASTE_REMOVAL = 'WASTE_REMOVAL', '粪便清理'

    pen = models.ForeignKey(Pen, on_delete=models.PROTECT, related_name='cleaning_records', verbose_name='栏区')
    cleaner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='cleaning_records', verbose_name='清洁人')
    cleaning_type = models.CharField(max_length=30, choices=CleaningType.choices, default=CleaningType.DAILY, verbose_name='清洁类型')
    cleaning_time = models.DateTimeField(default=timezone.now, verbose_name='清洁时间')
    duration_minutes = models.IntegerField(default=0, verbose_name='耗时(分钟)')
    disinfectant_used = models.CharField(max_length=100, blank=True, verbose_name='使用消毒剂')
    remarks = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '清洁记录'
        verbose_name_plural = verbose_name
        ordering = ['-cleaning_time']
        indexes = [
            models.Index(fields=['pen', 'cleaning_time']),
            models.Index(fields=['cleaning_time']),
        ]

    def __str__(self):
        return f'{self.pen.code} - {self.get_cleaning_type_display()}'


class Incident(models.Model):
    """
    异常事件表
    """
    class Severity(models.TextChoices):
        LOW = 'LOW', '低'
        MEDIUM = 'MEDIUM', '中'
        HIGH = 'HIGH', '高'
        CRITICAL = 'CRITICAL', '紧急'

    class Status(models.TextChoices):
        OPEN = 'OPEN', '待处理'
        IN_PROGRESS = 'IN_PROGRESS', '处理中'
        RESOLVED = 'RESOLVED', '已解决'
        CLOSED = 'CLOSED', '已关闭'

    pen = models.ForeignKey(Pen, on_delete=models.PROTECT, related_name='incidents', verbose_name='栏区')
    reporter = models.ForeignKey(User, on_delete=models.PROTECT, related_name='reported_incidents', verbose_name='上报人')
    title = models.CharField(max_length=200, verbose_name='事件标题')
    description = models.TextField(verbose_name='事件描述')
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM, verbose_name='严重程度')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name='处理状态')
    incident_time = models.DateTimeField(default=timezone.now, verbose_name='发生时间')
    inspection_record = models.ForeignKey(InspectionRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name='incidents', verbose_name='关联巡检记录')
    handler = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='handled_incidents', verbose_name='处理人')
    resolution = models.TextField(blank=True, verbose_name='处理方案')
    resolved_time = models.DateTimeField(null=True, blank=True, verbose_name='解决时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '异常事件'
        verbose_name_plural = verbose_name
        ordering = ['-incident_time']
        indexes = [
            models.Index(fields=['pen', 'incident_time']),
            models.Index(fields=['status', 'incident_time']),
            models.Index(fields=['incident_time']),
        ]

    def __str__(self):
        return f'[{self.get_severity_display()}] {self.pen.code} - {self.title}'


class IncidentUpdate(models.Model):
    """
    异常事件更新记录 - 记录事件处理过程中的每一次状态变更
    """
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='updates', verbose_name='异常事件')
    operator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='incident_updates', verbose_name='操作人')
    old_status = models.CharField(max_length=20, choices=Incident.Status.choices, verbose_name='原状态')
    new_status = models.CharField(max_length=20, choices=Incident.Status.choices, verbose_name='新状态')
    comment = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='操作时间')

    class Meta:
        verbose_name = '事件更新记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.incident.title} - {self.old_status} -> {self.new_status}'


class DailySnapshot(models.Model):
    """
    历史日报快照缓存 - 保存首次生成的历史快照，避免当前配置变更影响历史回看
    """
    snapshot_date = models.DateField(verbose_name='快照日期')
    pen_filter_key = models.CharField(max_length=50, default='all', verbose_name='栏区筛选键')
    data = models.JSONField(verbose_name='快照数据')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '历史日报快照'
        verbose_name_plural = verbose_name
        ordering = ['-snapshot_date', 'pen_filter_key']
        constraints = [
            models.UniqueConstraint(fields=['snapshot_date', 'pen_filter_key'], name='unique_daily_snapshot_filter'),
        ]
        indexes = [
            models.Index(fields=['snapshot_date', 'pen_filter_key']),
        ]

    def __str__(self):
        return f'{self.snapshot_date} - {self.pen_filter_key}'


class HealthScoreConfig(models.Model):
    """
    健康评分配置 - 管理员可配置权重、风险等级阈值和纳入评分的巡检项
    """
    class DimensionKey(models.TextChoices):
        INSPECTION_ABNORMAL = 'inspection_abnormal', '巡检异常数量'
        OPEN_INCIDENTS = 'open_incidents', '未处理异常事件'
        FEEDING_COMPLETION = 'feeding_completion', '喂养完成情况'
        CLEANING_COMPLETION = 'cleaning_completion', '清洁完成情况'
        CAPACITY_RATIO = 'capacity_ratio', '存栏容量占比'

    class RiskLevel(models.TextChoices):
        EXCELLENT = 'EXCELLENT', '优秀'
        GOOD = 'GOOD', '良好'
        NORMAL = 'NORMAL', '一般'
        WARNING = 'WARNING', '警告'
        DANGER = 'DANGER', '危险'

    dimension_key = models.CharField(max_length=50, choices=DimensionKey.choices, unique=True, verbose_name='评分维度')
    weight = models.FloatField(default=20.0, verbose_name='权重(%)')
    is_enabled = models.BooleanField(default=True, verbose_name='是否启用')
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '健康评分维度配置'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'dimension_key']

    def __str__(self):
        return f'{self.get_dimension_key_display()} (权重: {self.weight}%)'


class HealthScoreInspectionItem(models.Model):
    """
    纳入评分的巡检项配置 - 管理员可选择哪些巡检项参与评分计算
    """
    inspection_item = models.ForeignKey(InspectionItem, on_delete=models.CASCADE, related_name='score_configs', verbose_name='巡检项')
    penalty_per_abnormal = models.FloatField(default=5.0, verbose_name='每次异常扣分')
    is_enabled = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '评分巡检项配置'
        verbose_name_plural = verbose_name
        ordering = ['inspection_item__sort_order']

    def __str__(self):
        return f'{self.inspection_item.name} (扣{self.penalty_per_abnormal}分/次)'


class HealthScoreRiskThreshold(models.Model):
    """
    风险等级阈值配置 - 定义不同评分范围对应的风险等级
    """
    class RiskLevel(models.TextChoices):
        EXCELLENT = 'EXCELLENT', '优秀'
        GOOD = 'GOOD', '良好'
        NORMAL = 'NORMAL', '一般'
        WARNING = 'WARNING', '警告'
        DANGER = 'DANGER', '危险'

    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, unique=True, verbose_name='风险等级')
    min_score = models.FloatField(verbose_name='最低分(含)')
    max_score = models.FloatField(verbose_name='最高分(不含)')
    color = models.CharField(max_length=20, default='#00FF00', verbose_name='显示颜色')
    description = models.TextField(blank=True, verbose_name='描述')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '风险等级阈值配置'
        verbose_name_plural = verbose_name
        ordering = ['-min_score']

    def __str__(self):
        return f'{self.get_risk_level_display()} ({self.min_score}-{self.max_score})'


class HealthScoreRecord(models.Model):
    """
    栏区每日健康评分记录 - 系统自动计算，每日每个栏区一条记录
    """
    class RiskLevel(models.TextChoices):
        EXCELLENT = 'EXCELLENT', '优秀'
        GOOD = 'GOOD', '良好'
        NORMAL = 'NORMAL', '一般'
        WARNING = 'WARNING', '警告'
        DANGER = 'DANGER', '危险'

    score_date = models.DateField(verbose_name='评分日期')
    pen = models.ForeignKey(Pen, on_delete=models.CASCADE, related_name='health_scores', verbose_name='栏区')
    total_score = models.FloatField(default=100.0, verbose_name='总分')
    base_score = models.FloatField(default=100.0, verbose_name='基础分')
    deduction = models.FloatField(default=0.0, verbose_name='总扣分')
    addition = models.FloatField(default=0.0, verbose_name='总加分')
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices, default=RiskLevel.GOOD, verbose_name='风险等级')

    inspection_abnormal_score = models.FloatField(default=0.0, verbose_name='巡检异常扣分')
    open_incidents_score = models.FloatField(default=0.0, verbose_name='未处理事件扣分')
    feeding_completion_score = models.FloatField(default=100.0, verbose_name='喂养完成得分')
    cleaning_completion_score = models.FloatField(default=100.0, verbose_name='清洁完成得分')
    capacity_ratio_score = models.FloatField(default=100.0, verbose_name='存栏容量得分')

    inspection_abnormal_count = models.IntegerField(default=0, verbose_name='巡检异常数量')
    open_incidents_count = models.IntegerField(default=0, verbose_name='未处理事件数量')
    feeding_completion_rate = models.FloatField(default=0.0, verbose_name='喂养完成率(%)')
    cleaning_completion_rate = models.FloatField(default=0.0, verbose_name='清洁完成率(%)')
    capacity_ratio = models.FloatField(default=0.0, verbose_name='存栏容量占比(%)')

    is_calculated = models.BooleanField(default=False, verbose_name='是否已计算')
    calculated_at = models.DateTimeField(null=True, blank=True, verbose_name='计算时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '栏区健康评分记录'
        verbose_name_plural = verbose_name
        ordering = ['-score_date', 'pen__code']
        constraints = [
            models.UniqueConstraint(fields=['score_date', 'pen'], name='unique_daily_pen_score'),
        ]
        indexes = [
            models.Index(fields=['score_date', 'pen']),
            models.Index(fields=['risk_level']),
        ]

    def __str__(self):
        return f'{self.pen.code} - {self.score_date} ({self.total_score}分)'

    def get_risk_level_display_cn(self):
        return dict(HealthScoreRecord.RiskLevel.choices).get(self.risk_level, '未知')


class HealthScoreDetail(models.Model):
    """
    健康评分明细 - 记录每一项扣分/加分的具体原因和关联记录
    """
    class ScoreType(models.TextChoices):
        DEDUCTION = 'DEDUCTION', '扣分'
        ADDITION = 'ADDITION', '加分'
        RECOVERY = 'RECOVERY', '恢复加分'

    class SourceType(models.TextChoices):
        INSPECTION_ABNORMAL = 'inspection_abnormal', '巡检异常'
        OPEN_INCIDENT = 'open_incident', '未处理异常事件'
        INCIDENT_RESOLVED = 'incident_resolved', '异常事件解决'
        FEEDING_INCOMPLETE = 'feeding_incomplete', '喂养未完成'
        CLEANING_INCOMPLETE = 'cleaning_incomplete', '清洁未完成'
        CAPACITY_ABNORMAL = 'capacity_abnormal', '存栏容量异常'
        MANUAL_ADJUST = 'manual_adjust', '人工调整'

    score_record = models.ForeignKey(HealthScoreRecord, on_delete=models.CASCADE, related_name='details', verbose_name='评分记录')
    score_type = models.CharField(max_length=20, choices=ScoreType.choices, verbose_name='类型')
    source_type = models.CharField(max_length=30, choices=SourceType.choices, verbose_name='来源类型')
    score_value = models.FloatField(default=0.0, verbose_name='分值')
    description = models.CharField(max_length=500, verbose_name='描述')
    source_id = models.IntegerField(null=True, blank=True, verbose_name='关联源记录ID')
    inspection_item = models.ForeignKey(InspectionItem, null=True, blank=True, on_delete=models.SET_NULL, related_name='score_details', verbose_name='关联巡检项')
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name='score_details', verbose_name='关联异常事件')
    rectification_status = models.CharField(max_length=50, default='pending', verbose_name='整改状态')
    rectified_at = models.DateTimeField(null=True, blank=True, verbose_name='整改时间')
    operator = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='score_details', verbose_name='操作人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '健康评分明细'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['score_record']),
            models.Index(fields=['source_type']),
            models.Index(fields=['rectification_status']),
        ]

    def __str__(self):
        return f'{self.get_score_type_display()} {abs(self.score_value)}分 - {self.description}'
