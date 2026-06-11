from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_alter_incidentupdate_created_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailySnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('snapshot_date', models.DateField(verbose_name='快照日期')),
                ('pen_filter_key', models.CharField(default='all', max_length=50, verbose_name='栏区筛选键')),
                ('data', models.JSONField(verbose_name='快照数据')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '历史日报快照',
                'verbose_name_plural': '历史日报快照',
                'ordering': ['-snapshot_date', 'pen_filter_key'],
            },
        ),
        migrations.AddConstraint(
            model_name='dailysnapshot',
            constraint=models.UniqueConstraint(fields=('snapshot_date', 'pen_filter_key'), name='unique_daily_snapshot_filter'),
        ),
        migrations.AddIndex(
            model_name='dailysnapshot',
            index=models.Index(fields=['snapshot_date', 'pen_filter_key'], name='api_dailysn_snapsho_2fcb91_idx'),
        ),
    ]
