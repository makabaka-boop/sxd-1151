"""
日报导出服务
支持 Excel 和 PDF 格式导出
"""
from datetime import datetime
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from django.http import HttpResponse
from .services import snapshot_service


class ExportService:
    """导出服务"""

    STATUS_COLORS = {
        'NORMAL': '#00FF00',
        'PARTIAL': '#FFFF00',
        'ATTENTION': '#FFA500',
        'WARNING': '#FF0000',
    }

    STATUS_NAMES = {
        'NORMAL': '正常',
        'PARTIAL': '部分完成',
        'ATTENTION': '需关注',
        'WARNING': '异常',
    }

    @classmethod
    def export_daily_report_excel(cls, target_date, pen_id=None):
        """导出 Excel 格式的日报"""
        snapshot = snapshot_service.calculate_daily_snapshot(target_date, pen_id)

        wb = Workbook()
        ws = wb.active
        ws.title = f'巡检日报_{target_date}'

        header_font = Font(bold=True, size=14, color='FFFFFF')
        header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        sub_header_font = Font(bold=True, size=11)
        center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left_align = Alignment(horizontal='left', vertical='center', wrap_text=True)
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        ws.merge_cells('A1:L1')
        ws['A1'] = f'养殖场巡检日报 - {target_date}'
        ws['A1'].font = header_font
        ws['A1'].fill = header_fill
        ws['A1'].alignment = center_align
        ws.row_dimensions[1].height = 30

        summary_data = [
            ['汇总信息', '', '', '', '', '', '', '', '', '', '', ''],
            ['栏区总数', snapshot['total_pens'], '平均巡检完成率', f'{snapshot["average_inspection_completion_rate"]}%',
             '待处理异常事件', snapshot['total_open_incidents'], '今日异常总数', snapshot['total_abnormal_count'],
             '导出时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '', ''],
        ]

        row = 3
        for row_data in summary_data:
            for col, value in enumerate(row_data, 1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.alignment = center_align
                cell.border = thin_border
                if col == 1:
                    cell.font = sub_header_font
            row += 1

        row += 1
        ws.cell(row=row, column=1, value='栏区详情').font = sub_header_font
        row += 1

        detail_headers = [
            '栏区编号', '栏区名称', '养殖类型', '当前数量',
            '巡检完成率', '巡检次数', '异常指标数',
            '喂养次数', '总投喂量(kg)',
            '清洁次数', '总耗时(分钟)',
            '待处理事件', '今日新事件', '整体状态'
        ]

        for col, header in enumerate(detail_headers, 1):
            cell = ws.cell(row=row, column=col, value=header)
            cell.font = sub_header_font
            cell.alignment = center_align
            cell.border = thin_border
            cell.fill = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')
        row += 1

        for pen_snap in snapshot['pen_snapshots']:
            status_color = cls.STATUS_COLORS.get(pen_snap['overall_status'], '#FFFFFF')
            status_name = cls.STATUS_NAMES.get(pen_snap['overall_status'], '未知')

            row_data = [
                pen_snap['pen_code'],
                pen_snap['pen_name'],
                pen_snap['livestock_type'],
                pen_snap['current_count'],
                f'{pen_snap["inspection"]["completion_rate"]}%',
                pen_snap['inspection']['inspection_count'],
                pen_snap['inspection']['abnormal_count'],
                pen_snap['feeding']['feeding_count'],
                pen_snap['feeding']['total_feed_amount'],
                pen_snap['cleaning']['cleaning_count'],
                pen_snap['cleaning']['total_duration_minutes'],
                pen_snap['incidents']['open_count'],
                pen_snap['incidents']['new_today_count'],
                status_name,
            ]

            for col, value in enumerate(row_data, 1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.alignment = center_align if col != 2 else left_align
                cell.border = thin_border
                if col == 14:
                    excel_color = status_color.lstrip('#')
                    cell.fill = PatternFill(start_color=excel_color, end_color=excel_color, fill_type='solid')
            row += 1

        row += 1
        ws.cell(row=row, column=1, value='异常事件详情').font = sub_header_font
        row += 1

        incident_headers = [
            '栏区编号', '事件标题', '严重程度', '状态',
            '发生时间', '上报人', '处理状态', '处理人', '持续时间(小时)'
        ]

        for col, header in enumerate(incident_headers, 1):
            cell = ws.cell(row=row, column=col, value=header)
            cell.font = sub_header_font
            cell.alignment = center_align
            cell.border = thin_border
            cell.fill = PatternFill(start_color='F8CBAD', end_color='F8CBAD', fill_type='solid')
        row += 1

        for pen_snap in snapshot['pen_snapshots']:
            all_incidents = (pen_snap['incidents']['open_incidents'] +
                             pen_snap['incidents']['in_progress_incidents'] +
                             pen_snap['incidents']['new_today_incidents'])
            for incident in all_incidents:
                row_data = [
                    pen_snap['pen_code'],
                    incident['title'],
                    incident['severity_display'],
                    incident['status_display'],
                    incident['incident_time'],
                    incident['reporter_name'],
                    incident['status_display'],
                    '',
                    ''
                ]
                for col, value in enumerate(row_data, 1):
                    cell = ws.cell(row=row, column=col, value=value)
                    cell.alignment = center_align if col != 2 else left_align
                    cell.border = thin_border
                row += 1

        column_widths = [12, 20, 10, 10, 12, 10, 12, 10, 14, 10, 14, 12, 12, 10]
        for col, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = width

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="巡检日报_{target_date}.xlsx"'
        return response

    @classmethod
    def export_daily_report_pdf(cls, target_date, pen_id=None):
        """导出 PDF 格式的日报"""
        snapshot = snapshot_service.calculate_daily_snapshot(target_date, pen_id)

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            alignment=1,
            spaceAfter=20
        )
        section_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#4472C4'),
            spaceBefore=10,
            spaceAfter=10
        )

        story = []

        story.append(Paragraph(f'养殖场巡检日报 - {target_date}', title_style))
        story.append(Spacer(1, 0.5 * cm))

        summary_data = [
            ['栏区总数', str(snapshot['total_pens']),
             '平均巡检完成率', f'{snapshot["average_inspection_completion_rate"]}%',
             '待处理异常事件', str(snapshot['total_open_incidents']),
             '今日异常总数', str(snapshot['total_abnormal_count'])],
            ['导出时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '', '', '', '', '', ''],
        ]

        summary_table = Table(summary_data, colWidths=[2.5 * cm, 2 * cm, 3.5 * cm, 2 * cm, 3 * cm, 2 * cm, 3 * cm, 2 * cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D9E2F3')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.8 * cm))

        story.append(Paragraph('栏区详情', section_style))

        detail_headers = [
            '栏区编号', '栏区名称', '养殖类型', '当前数量',
            '巡检完成率', '巡检次数', '异常指标',
            '喂养次数', '投喂量(kg)',
            '清洁次数', '耗时(分)',
            '待处理', '新事件', '状态'
        ]

        detail_data = [detail_headers]
        for pen_snap in snapshot['pen_snapshots']:
            status_name = cls.STATUS_NAMES.get(pen_snap['overall_status'], '未知')
            detail_data.append([
                pen_snap['pen_code'],
                pen_snap['pen_name'],
                pen_snap['livestock_type'],
                str(pen_snap['current_count']),
                f'{pen_snap["inspection"]["completion_rate"]}%',
                str(pen_snap['inspection']['inspection_count']),
                str(pen_snap['inspection']['abnormal_count']),
                str(pen_snap['feeding']['feeding_count']),
                str(pen_snap['feeding']['total_feed_amount']),
                str(pen_snap['cleaning']['cleaning_count']),
                str(pen_snap['cleaning']['total_duration_minutes']),
                str(pen_snap['incidents']['open_count']),
                str(pen_snap['incidents']['new_today_count']),
                status_name,
            ])

        detail_table = Table(detail_data, colWidths=[1.6 * cm] * 14)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        for i, pen_snap in enumerate(snapshot['pen_snapshots'], 1):
            status = pen_snap['overall_status']
            color = cls.STATUS_COLORS.get(status, '#FFFFFF')
            style_cmds.append(('BACKGROUND', (13, i), (13, i), colors.HexColor(color)))

        detail_table.setStyle(TableStyle(style_cmds))
        story.append(detail_table)
        story.append(Spacer(1, 0.8 * cm))

        story.append(Paragraph('异常事件详情', section_style))

        incident_headers = [
            '栏区编号', '事件标题', '严重程度', '状态', '发生时间', '上报人'
        ]

        all_incidents = []
        for pen_snap in snapshot['pen_snapshots']:
            pen_incidents = (pen_snap['incidents']['open_incidents'] +
                             pen_snap['incidents']['in_progress_incidents'] +
                             pen_snap['incidents']['new_today_incidents'])
            for incident in pen_incidents:
                all_incidents.append([
                    pen_snap['pen_code'],
                    Paragraph(incident['title'], styles['Normal']),
                    incident['severity_display'],
                    incident['status_display'],
                    incident['incident_time'][:16].replace('T', ' '),
                    incident['reporter_name'],
                ])

        if all_incidents:
            incident_data = [incident_headers] + all_incidents
            incident_table = Table(
                incident_data,
                colWidths=[1.8 * cm, 6 * cm, 1.8 * cm, 1.8 * cm, 3 * cm, 2 * cm]
            )
            incident_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F8CBAD')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(incident_table)
        else:
            story.append(Paragraph('今日无异常事件', styles['Normal']))

        doc.build(story)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="巡检日报_{target_date}.pdf"'
        return response

    @classmethod
    def export_daily_report(cls, target_date, format_type='excel', pen_id=None):
        """统一导出接口"""
        if format_type.lower() == 'pdf':
            return cls.export_daily_report_pdf(target_date, pen_id)
        else:
            return cls.export_daily_report_excel(target_date, pen_id)


export_service = ExportService()
