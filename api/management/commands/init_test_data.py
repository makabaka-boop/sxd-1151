"""
初始化测试数据命令
创建测试用户、栏区、巡检项和历史测试数据
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from api.models import (
    Pen, InspectionItem, InspectionRecord, InspectionItemValue,
    FeedingRecord, CleaningRecord, Incident
)
from datetime import datetime, timedelta
import random

User = get_user_model()


class Command(BaseCommand):
    help = '初始化测试数据'

    def handle(self, *args, **options):
        self.stdout.write('开始初始化测试数据...')

        self.create_users()
        self.create_pens()
        self.create_inspection_items()
        self.create_historical_data(days=7)

        self.stdout.write(self.style.SUCCESS('测试数据初始化完成！'))

    def create_users(self):
        """创建三级权限测试用户"""
        self.stdout.write('创建测试用户...')

        users_data = [
            {'username': 'admin', 'real_name': '系统管理员', 'role': 'ADMIN', 'password': 'admin123', 'is_staff': True},
            {'username': 'worker1', 'real_name': '张三', 'role': 'FIELD_WORKER', 'password': '123456'},
            {'username': 'worker2', 'real_name': '李四', 'role': 'FIELD_WORKER', 'password': '123456'},
            {'username': 'observer1', 'real_name': '王观察员', 'role': 'OBSERVER', 'password': '123456'},
            {'username': 'observer2', 'real_name': '赵分析员', 'role': 'OBSERVER', 'password': '123456'},
        ]

        for user_data in users_data:
            if not User.objects.filter(username=user_data['username']).exists():
                user = User.objects.create_user(
                    username=user_data['username'],
                    real_name=user_data['real_name'],
                    role=user_data['role'],
                    password=user_data['password'],
                    is_staff=user_data.get('is_staff', False)
                )
                self.stdout.write(f'  创建用户: {user.username} ({user.get_role_display()})')
            else:
                self.stdout.write(f'  用户已存在: {user_data["username"]}')

    def create_pens(self):
        """创建测试栏区"""
        self.stdout.write('创建测试栏区...')

        pens_data = [
            {'code': 'A-01', 'name': 'A区1号栏', 'livestock_type': '生猪', 'capacity': 50, 'current_count': 45},
            {'code': 'A-02', 'name': 'A区2号栏', 'livestock_type': '生猪', 'capacity': 50, 'current_count': 48},
            {'code': 'A-03', 'name': 'A区3号栏', 'livestock_type': '生猪', 'capacity': 50, 'current_count': 42},
            {'code': 'B-01', 'name': 'B区1号栏', 'livestock_type': '生猪', 'capacity': 60, 'current_count': 55},
            {'code': 'B-02', 'name': 'B区2号栏', 'livestock_type': '生猪', 'capacity': 60, 'current_count': 58},
            {'code': 'C-01', 'name': 'C区1号栏', 'livestock_type': '奶牛', 'capacity': 30, 'current_count': 25},
            {'code': 'C-02', 'name': 'C区2号栏', 'livestock_type': '奶牛', 'capacity': 30, 'current_count': 28},
        ]

        for pen_data in pens_data:
            if not Pen.objects.filter(code=pen_data['code']).exists():
                pen = Pen.objects.create(**pen_data)
                self.stdout.write(f'  创建栏区: {pen.code} - {pen.name}')
            else:
                self.stdout.write(f'  栏区已存在: {pen_data["code"]}')

    def create_inspection_items(self):
        """创建测试巡检项"""
        self.stdout.write('创建测试巡检项...')

        items_data = [
            {'code': 'TEMP', 'name': '温度', 'value_type': 'NUMERIC', 'unit': '°C', 'min_value': 18.0, 'max_value': 28.0, 'sort_order': 1},
            {'code': 'HUMIDITY', 'name': '湿度', 'value_type': 'NUMERIC', 'unit': '%', 'min_value': 40.0, 'max_value': 70.0, 'sort_order': 2},
            {'code': 'FEED_REMAIN', 'name': '饲料剩余量', 'value_type': 'NUMERIC', 'unit': 'kg', 'min_value': 10.0, 'sort_order': 3},
            {'code': 'WATER', 'name': '饮水温度', 'value_type': 'NUMERIC', 'unit': '°C', 'min_value': 10.0, 'max_value': 25.0, 'sort_order': 4},
            {'code': 'AMMONIA', 'name': '氨气浓度', 'value_type': 'NUMERIC', 'unit': 'ppm', 'max_value': 20.0, 'sort_order': 5},
            {'code': 'HEALTH', 'name': '健康状况', 'value_type': 'BOOLEAN', 'sort_order': 6},
            {'code': 'EQUIPMENT', 'name': '设备状态', 'value_type': 'CHOICE', 'choice_options': ['正常', '需维护', '故障'], 'sort_order': 7},
            {'code': 'REMARKS', 'name': '其他备注', 'value_type': 'TEXT', 'sort_order': 8},
        ]

        for item_data in items_data:
            if not InspectionItem.objects.filter(code=item_data['code']).exists():
                item = InspectionItem.objects.create(**item_data)
                self.stdout.write(f'  创建巡检项: {item.code} - {item.name}')
            else:
                self.stdout.write(f'  巡检项已存在: {item_data["code"]}')

    def create_historical_data(self, days=7):
        """创建历史测试数据"""
        self.stdout.write(f'创建过去 {days} 天的历史数据...')

        field_workers = User.objects.filter(role='FIELD_WORKER')
        pens = Pen.objects.filter(is_active=True)
        inspection_items = InspectionItem.objects.filter(is_active=True)

        base_date = timezone.now().date()

        for day_offset in range(days):
            current_date = base_date - timedelta(days=day_offset)
            self.stdout.write(f'  创建 {current_date.isoformat()} 的数据...')

            for pen in pens:
                for worker in field_workers:
                    if random.random() < 0.8:
                        self._create_daily_records(current_date, pen, worker, inspection_items)

            if random.random() < 0.4:
                self._create_incident(current_date, random.choice(list(pens)), random.choice(list(field_workers)))

    def _create_daily_records(self, date, pen, worker, inspection_items):
        """创建单日记录"""
        inspection_count = random.randint(1, 3)

        for i in range(inspection_count):
            hour = random.randint(6, 18)
            minute = random.randint(0, 59)
            inspection_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

            record = InspectionRecord.objects.create(
                pen=pen,
                inspector=worker,
                inspection_time=inspection_time,
                remarks=f'日常巡检' if random.random() < 0.3 else ''
            )

            for item in inspection_items:
                if random.random() < 0.95:
                    is_abnormal = False
                    numeric_value = None
                    boolean_value = None
                    text_value = ''

                    if item.value_type == 'NUMERIC':
                        if item.min_value and item.max_value:
                            base = (item.min_value + item.max_value) / 2
                            variance = (item.max_value - item.min_value) * 0.3
                            numeric_value = round(random.uniform(base - variance, base + variance), 2)
                            if random.random() < 0.1:
                                numeric_value = random.choice([
                                    item.min_value - random.uniform(1, 5),
                                    item.max_value + random.uniform(1, 5)
                                ])
                                is_abnormal = True
                        else:
                            numeric_value = round(random.uniform(5, 50), 2)
                    elif item.value_type == 'BOOLEAN':
                        boolean_value = random.random() < 0.9
                        if not boolean_value:
                            is_abnormal = True
                    elif item.value_type == 'CHOICE':
                        choices = item.choice_options or ['正常']
                        text_value = random.choice(choices)
                        if text_value != '正常':
                            is_abnormal = True
                    elif item.value_type == 'TEXT':
                        if random.random() < 0.3:
                            text_value = '一切正常'

                    InspectionItemValue.objects.create(
                        record=record,
                        inspection_item=item,
                        numeric_value=numeric_value,
                        boolean_value=boolean_value,
                        text_value=text_value,
                        is_abnormal=is_abnormal
                    )

        feeding_count = random.randint(2, 4)
        for i in range(feeding_count):
            hour = random.choice([6, 10, 14, 18])
            minute = random.randint(0, 30)
            feeding_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

            FeedingRecord.objects.create(
                pen=pen,
                feeder=worker,
                feed_type=random.choice(['配合饲料', '玉米', '豆粕']),
                feed_amount=round(random.uniform(20, 50), 2),
                feeding_time=feeding_time
            )

        if random.random() < 0.7:
            hour = random.randint(8, 16)
            minute = random.randint(0, 59)
            cleaning_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

            CleaningRecord.objects.create(
                pen=pen,
                cleaner=worker,
                cleaning_type=random.choice(['DAILY', 'DISINFECTION', 'WASTE_REMOVAL']),
                cleaning_time=cleaning_time,
                duration_minutes=random.randint(20, 60),
                disinfectant_used=random.choice(['84消毒液', '过氧乙酸', '']) if random.random() < 0.5 else ''
            )

    def _create_incident(self, date, pen, reporter):
        """创建异常事件"""
        hour = random.randint(8, 18)
        minute = random.randint(0, 59)
        incident_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

        incident_titles = [
            ('发现一头猪精神萎靡', 'LOW'),
            ('料线设备故障', 'HIGH'),
            ('温度异常偏高', 'MEDIUM'),
            ('发现病猪', 'CRITICAL'),
            ('饮水器漏水', 'LOW'),
            ('氨气浓度超标', 'MEDIUM'),
        ]

        title, severity = random.choice(incident_titles)

        status_choices = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED']
        status_weights = [0.3, 0.2, 0.3, 0.2]
        status = random.choices(status_choices, weights=status_weights)[0]

        handler = User.objects.filter(role__in=['ADMIN', 'FIELD_WORKER']).order_by('?').first()

        incident = Incident.objects.create(
            pen=pen,
            reporter=reporter,
            title=title,
            description=f'在巡检中发现：{title}，请及时处理。',
            severity=severity,
            status=status,
            incident_time=incident_time,
            handler=handler if status != 'OPEN' else None,
            resolution=f'已妥善处理，情况已控制。' if status in ['RESOLVED', 'CLOSED'] else '',
            resolved_time=incident_time + timedelta(hours=random.randint(1, 6)) if status in ['RESOLVED', 'CLOSED'] else None
        )

        self.stdout.write(f'    创建事件: {pen.code} - {title} ({severity})')
