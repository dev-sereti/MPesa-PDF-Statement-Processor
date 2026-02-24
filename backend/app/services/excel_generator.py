# backend/app/services/excel_generator.py
import io
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import openpyxl
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.series import DataPoint

from app.services.statement_parser import ParsedStatement, MPesaTransaction, TransactionType

logger = logging.getLogger(__name__)


class MPesaExcelGenerator:
    """
    Generates professionally formatted Excel files from parsed MPesa statements.
    
    Features:
    - Summary dashboard sheet
    - Detailed transactions sheet
    - Monthly breakdown sheet
    - Transaction type analysis
    - Charts and visualizations
    """
    
    # Color scheme (MPesa green)
    COLORS = {
        'mpesa_green': '4CAF50',
        'mpesa_dark_green': '388E3C',
        'header_bg': '1B5E20',
        'header_text': 'FFFFFF',
        'alt_row': 'F1F8E9',
        'positive': 'E8F5E9',
        'negative': 'FFEBEE',
        'border': 'BDBDBD',
        'summary_bg': 'F9FBE7',
        'warning': 'FFF9C4',
        'total_row': 'DCEDC8',
    }
    
    def generate(self, statement: ParsedStatement) -> bytes:
        """Generate Excel file and return as bytes."""
        wb = openpyxl.Workbook()
        
        # Create sheets
        self._create_summary_sheet(wb, statement)
        self._create_transactions_sheet(wb, statement)
        self._create_monthly_breakdown_sheet(wb, statement)
        self._create_type_analysis_sheet(wb, statement)
        
        # Save to buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        
        logger.info(f"Generated Excel with {len(statement.transactions)} transactions")
        return buffer.getvalue()
    
    def _create_summary_sheet(self, wb: openpyxl.Workbook, statement: ParsedStatement) -> None:
        """Create executive summary dashboard."""
        ws = wb.active
        ws.title = "Summary"
        
        # Title
        ws.merge_cells('A1:F1')
        title_cell = ws['A1']
        title_cell.value = "M-PESA STATEMENT ANALYSIS"
        title_cell.font = Font(bold=True, size=18, color=self.COLORS['header_text'])
        title_cell.fill = PatternFill("solid", fgColor=self.COLORS['header_bg'])
        title_cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 40
        
        # Generated date
        ws.merge_cells('A2:F2')
        ws['A2'].value = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ws['A2'].font = Font(italic=True, size=10, color='666666')
        ws['A2'].alignment = Alignment(horizontal='center')
        
        row = 4
        
        # Account information
        self._add_section_header(ws, row, 'A', 'D', "ACCOUNT INFORMATION")
        row += 1
        
        account_info = [
            ("Account Name", statement.metadata.account_name or "N/A"),
            ("Phone Number", statement.metadata.phone_number or "N/A"),
            ("Statement Period", self._format_period(statement.metadata)),
            ("Total Transactions", str(statement.metadata.transaction_count)),
        ]
        
        for label, value in account_info:
            ws[f'A{row}'] = label
            ws[f'A{row}'].font = Font(bold=True)
            ws[f'B{row}'] = value
            ws[f'B{row}'].fill = PatternFill("solid", fgColor=self.COLORS['summary_bg'])
            ws.merge_cells(f'B{row}:D{row}')
            row += 1
        
        row += 1
        
        # Financial summary
        self._add_section_header(ws, row, 'A', 'D', "FINANCIAL SUMMARY")
        row += 1
        
        summary_data = [
            ("Opening Balance (KES)", statement.metadata.opening_balance),
            ("Closing Balance (KES)", statement.metadata.closing_balance),
            ("Total Money In (KES)", statement.metadata.total_paid_in),
            ("Total Money Out (KES)", statement.metadata.total_withdrawn),
            ("Net Flow (KES)", 
             (statement.metadata.total_paid_in or Decimal('0')) - 
             (statement.metadata.total_withdrawn or Decimal('0'))),
        ]
        
        for label, value in summary_data:
            ws[f'A{row}'] = label
            ws[f'A{row}'].font = Font(bold=True)
            
            if value is not None:
                ws[f'C{row}'] = float(value)
                ws[f'C{row}'].number_format = '#,##0.00'
                ws[f'C{row}'].font = Font(
                    bold=True,
                    color='2E7D32' if (isinstance(value, Decimal) and value >= 0) else 'C62828'
                )
            else:
                ws[f'C{row}'] = "N/A"
            
            ws.merge_cells(f'C{row}:D{row}')
            row += 1
        
        row += 2
        
        # Transaction type breakdown
        self._add_section_header(ws, row, 'A', 'D', "TRANSACTION TYPE BREAKDOWN")
        row += 1
        
        type_totals = self._calculate_type_totals(statement.transactions)
        
        # Headers
        for col, header in enumerate(['Transaction Type', 'Count', 'Amount In (KES)', 'Amount Out (KES)'], 1):
            cell = ws.cell(row=row, column=col, value=header)
            cell.font = Font(bold=True, color=self.COLORS['header_text'])
            cell.fill = PatternFill("solid", fgColor=self.COLORS['mpesa_green'])
            cell.alignment = Alignment(horizontal='center')
        row += 1
        
        alt = False
        for txn_type, data in sorted(type_totals.items(), key=lambda x: -x[1]['count']):
            bg = self.COLORS['alt_row'] if alt else 'FFFFFF'
            for col, value in enumerate([
                txn_type.value,
                data['count'],
                float(data['paid_in']),
                float(data['withdrawn'])
            ], 1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.fill = PatternFill("solid", fgColor=bg)
                if col >= 3:
                    cell.number_format = '#,##0.00'
            row += 1
            alt = not alt
        
        # Set column widths
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 15
        
        self._apply_borders(ws, 4, row - 1, 1, 4)
    
    def _create_transactions_sheet(
        self, 
        wb: openpyxl.Workbook, 
        statement: ParsedStatement
    ) -> None:
        """Create detailed transactions sheet with all data."""
        ws = wb.create_sheet("Transactions")
        
        # Headers
        headers = [
            "Receipt No.", "Date", "Time", "Description",
            "Transaction Type", "Counterparty", "Reference",
            "Paid In (KES)", "Withdrawn (KES)", "Balance (KES)"
        ]
        
        # Header row
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, size=11, color=self.COLORS['header_text'])
            cell.fill = PatternFill("solid", fgColor=self.COLORS['header_bg'])
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        
        ws.row_dimensions[1].height = 35
        
        # Data rows
        for row_idx, txn in enumerate(statement.transactions, 2):
            alt_bg = self.COLORS['alt_row'] if row_idx % 2 == 0 else 'FFFFFF'
            
            # Color code by transaction type
            if txn.paid_in and txn.paid_in > 0:
                row_bg = self.COLORS['positive']
            elif txn.withdrawn and txn.withdrawn > 0:
                row_bg = self.COLORS['negative']
            else:
                row_bg = alt_bg
            
            row_data = [
                txn.receipt_no,
                txn.completion_time.strftime("%Y-%m-%d") if txn.completion_time else "",
                txn.completion_time.strftime("%H:%M:%S") if txn.completion_time else "",
                txn.description[:150] if txn.description else "",
                txn.transaction_type.value,
                txn.counterparty[:50] if txn.counterparty else "",
                txn.reference,
                float(txn.paid_in) if txn.paid_in else 0.0,
                float(txn.withdrawn) if txn.withdrawn else 0.0,
                float(txn.balance) if txn.balance else "",
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                cell.fill = PatternFill("solid", fgColor=row_bg)
                
                # Format amount columns
                if col in [8, 9, 10]:
                    cell.number_format = '#,##0.00'
                    cell.alignment = Alignment(horizontal='right')
                elif col == 4:  # Description
                    cell.alignment = Alignment(wrap_text=True)
                
                # Highlight amounts
                if col == 8 and isinstance(value, float) and value > 0:
                    cell.font = Font(color='1B5E20', bold=True)
                elif col == 9 and isinstance(value, float) and value > 0:
                    cell.font = Font(color='B71C1C', bold=True)
        
        # Totals row
        total_row = len(statement.transactions) + 2
        ws.cell(row=total_row, column=7, value="TOTALS").font = Font(bold=True)
        
        total_in = sum(
            float(t.paid_in) for t in statement.transactions if t.paid_in
        )
        total_out = sum(
            float(t.withdrawn) for t in statement.transactions if t.withdrawn
        )
        
        for col, value in [(8, total_in), (9, total_out)]:
            cell = ws.cell(row=total_row, column=col, value=value)
            cell.number_format = '#,##0.00'
            cell.font = Font(bold=True, size=12)
            cell.fill = PatternFill("solid", fgColor=self.COLORS['total_row'])
        
        # Set column widths
        column_widths = [18, 12, 10, 45, 20, 25, 15, 16, 16, 16]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width
        
        # Freeze header row
        ws.freeze_panes = 'A2'
        
        # Auto-filter
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    
    def _create_monthly_breakdown_sheet(
        self, 
        wb: openpyxl.Workbook, 
        statement: ParsedStatement
    ) -> None:
        """Create monthly aggregation sheet."""
        ws = wb.create_sheet("Monthly Breakdown")
        
        # Aggregate by month
        monthly_data = {}
        for txn in statement.transactions:
            if not txn.completion_time:
                continue
            
            month_key = txn.completion_time.strftime("%Y-%m")
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    'label': txn.completion_time.strftime("%B %Y"),
                    'count': 0,
                    'paid_in': Decimal('0'),
                    'withdrawn': Decimal('0'),
                }
            
            monthly_data[month_key]['count'] += 1
            if txn.paid_in:
                monthly_data[month_key]['paid_in'] += txn.paid_in
            if txn.withdrawn:
                monthly_data[month_key]['withdrawn'] += txn.withdrawn
        
        # Header
        headers = ["Month", "Transactions", "Total Paid In (KES)", "Total Withdrawn (KES)", "Net (KES)"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color=self.COLORS['header_text'])
            cell.fill = PatternFill("solid", fgColor=self.COLORS['header_bg'])
            cell.alignment = Alignment(horizontal='center')
        
        # Data
        for row_idx, (month_key, data) in enumerate(sorted(monthly_data.items()), 2):
            net = data['paid_in'] - data['withdrawn']
            row_data = [
                data['label'],
                data['count'],
                float(data['paid_in']),
                float(data['withdrawn']),
                float(net)
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                if col >= 3:
                    cell.number_format = '#,##0.00'
                if col == 5:  # Net column
                    cell.font = Font(
                        color='1B5E20' if net >= 0 else 'B71C1C',
                        bold=True
                    )
        
        # Add chart if data available
        if len(monthly_data) > 1:
            self._add_monthly_chart(ws, len(monthly_data))
        
        # Column widths
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 22
        ws.column_dimensions['D'].width = 22
        ws.column_dimensions['E'].width = 18
    
    def _add_monthly_chart(self, ws, data_rows: int) -> None:
        """Add bar chart for monthly breakdown."""
        chart = BarChart()
        chart.type = "col"
        chart.grouping = "clustered"
        chart.title = "Monthly Income vs Expense"
        chart.y_axis.title = "Amount (KES)"
        chart.x_axis.title = "Month"
        chart.style = 10
        
        # Data references
        paid_in_data = Reference(ws, min_col=3, max_col=3, min_row=1, max_row=data_rows + 1)
        withdrawn_data = Reference(ws, min_col=4, max_col=4, min_row=1, max_row=data_rows + 1)
        months = Reference(ws, min_col=1, min_row=2, max_row=data_rows + 1)
        
        chart.add_data(paid_in_data, titles_from_data=True)
        chart.add_data(withdrawn_data, titles_from_data=True)
        chart.set_categories(months)
        
        chart.series[0].graphicalProperties.solidFill = self.COLORS['mpesa_green']
        chart.series[1].graphicalProperties.solidFill = 'EF5350'
        
        chart.width = 20
        chart.height = 12
        
        ws.add_chart(chart, f"G2")
    
    def _create_type_analysis_sheet(
        self,
        wb: openpyxl.Workbook,
        statement: ParsedStatement
    ) -> None:
        """Create transaction type analysis sheet."""
        ws = wb.create_sheet("Type Analysis")
        
        type_totals = self._calculate_type_totals(statement.transactions)
        
        headers = ["Transaction Type", "Count", "% of Total", "Paid In (KES)", "Withdrawn (KES)", "Net (KES)"]
        total_count = sum(d['count'] for d in type_totals.values())
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color=self.COLORS['header_text'])
            cell.fill = PatternFill("solid", fgColor=self.COLORS['header_bg'])
            cell.alignment = Alignment(horizontal='center')
        
        for row_idx, (txn_type, data) in enumerate(
            sorted(type_totals.items(), key=lambda x: -x[1]['count']), 2
        ):
            pct = (data['count'] / total_count * 100) if total_count > 0 else 0
            net = data['paid_in'] - data['withdrawn']
            
            row_data = [
                txn_type.value,
                data['count'],
                f"{pct:.1f}%",
                float(data['paid_in']),
                float(data['withdrawn']),
                float(net)
            ]
            
            for col, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                if col in [4, 5, 6]:
                    cell.number_format = '#,##0.00'
        
        # Column widths
        for col, width in enumerate([25, 10, 12, 20, 20, 18], 1):
            ws.column_dimensions[get_column_letter(col)].width = width
    
    # ─── Helper Methods ───────────────────────────────────────
    
    def _add_section_header(
        self, ws, row: int, start_col: str, end_col: str, title: str
    ) -> None:
        ws.merge_cells(f'{start_col}{row}:{end_col}{row}')
        cell = ws[f'{start_col}{row}']
        cell.value = title
        cell.font = Font(bold=True, size=12, color=self.COLORS['header_text'])
        cell.fill = PatternFill("solid", fgColor=self.COLORS['mpesa_green'])
        cell.alignment = Alignment(horizontal='left', indent=1)
        ws.row_dimensions[row].height = 25
    
    def _apply_borders(
        self, ws, start_row: int, end_row: int, start_col: int, end_col: int
    ) -> None:
        border = Border(
            left=Side(style='thin', color=self.COLORS['border']),
            right=Side(style='thin', color=self.COLORS['border']),
            top=Side(style='thin', color=self.COLORS['border']),
            bottom=Side(style='thin', color=self.COLORS['border'])
        )
        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                ws.cell(row=row, column=col).border = border
    
    def _format_period(self, metadata) -> str:
        if metadata.statement_period_start and metadata.statement_period_end:
            return (
                f"{metadata.statement_period_start.strftime('%d %b %Y')} - "
                f"{metadata.statement_period_end.strftime('%d %b %Y')}"
            )
        return "N/A"
    
    def _calculate_type_totals(self, transactions: List[MPesaTransaction]) -> dict:
        totals = {}
        for txn in transactions:
            if txn.transaction_type not in totals:
                totals[txn.transaction_type] = {
                    'count': 0,
                    'paid_in': Decimal('0'),
                    'withdrawn': Decimal('0')
                }
            totals[txn.transaction_type]['count'] += 1
            if txn.paid_in:
                totals[txn.transaction_type]['paid_in'] += txn.paid_in
            if txn.withdrawn:
                totals[txn.transaction_type]['withdrawn'] += txn.withdrawn
        return totals