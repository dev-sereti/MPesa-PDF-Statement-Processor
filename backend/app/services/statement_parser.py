# backend/app/services/statement_parser.py
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Dict, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class TransactionType(str, Enum):
    SENT = "Money Sent"
    RECEIVED = "Money Received"
    PAYBILL = "Paybill Payment"
    TILL = "Buy Goods (Till)"
    AIRTIME = "Airtime Purchase"
    WITHDRAWAL = "Withdrawal"
    DEPOSIT = "Deposit"
    REVERSAL = "Reversal"
    FULIZA = "Fuliza"
    LOAN = "Loan"
    CHARGES = "Transaction Charges"
    OTHER = "Other"


@dataclass
class MPesaTransaction:
    """Represents a single MPesa transaction."""
    receipt_no: str = ""
    completion_time: Optional[datetime] = None
    description: str = ""
    paid_in: Optional[Decimal] = None
    withdrawn: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    transaction_type: TransactionType = TransactionType.OTHER
    counterparty: str = ""
    reference: str = ""
    
    def to_dict(self) -> dict:
        return {
            "Receipt No.": self.receipt_no,
            "Completion Time": self.completion_time.strftime("%Y-%m-%d %H:%M:%S") if self.completion_time else "",
            "Date": self.completion_time.strftime("%Y-%m-%d") if self.completion_time else "",
            "Time": self.completion_time.strftime("%H:%M:%S") if self.completion_time else "",
            "Description": self.description,
            "Transaction Type": self.transaction_type.value,
            "Counterparty": self.counterparty,
            "Reference": self.reference,
            "Paid In (KES)": float(self.paid_in) if self.paid_in else 0.0,
            "Withdrawn (KES)": float(self.withdrawn) if self.withdrawn else 0.0,
            "Balance (KES)": float(self.balance) if self.balance else 0.0,
        }


@dataclass
class StatementMetadata:
    """MPesa statement metadata."""
    account_name: str = ""
    phone_number: str = ""
    statement_period_start: Optional[datetime] = None
    statement_period_end: Optional[datetime] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_paid_in: Optional[Decimal] = None
    total_withdrawn: Optional[Decimal] = None
    transaction_count: int = 0


@dataclass
class ParsedStatement:
    """Complete parsed MPesa statement."""
    metadata: StatementMetadata = field(default_factory=StatementMetadata)
    transactions: List[MPesaTransaction] = field(default_factory=list)
    parsing_warnings: List[str] = field(default_factory=list)
    raw_lines_processed: int = 0


class MPesaStatementParser:
    """
    Parses MPesa PDF statement text into structured transaction data.
    
    Handles multiple MPesa statement formats including:
    - Standard monthly statements
    - Custom date range statements
    - Both table and non-table formats
    """
    
    # Regex patterns for MPesa data
    RECEIPT_PATTERN = re.compile(r'\b([A-Z]{2,3}\d{8,12})\b')
    AMOUNT_PATTERN = re.compile(r'(?:Ksh\.?|KES)\s*([\d,]+\.?\d{0,2})', re.IGNORECASE)
    PLAIN_AMOUNT_PATTERN = re.compile(r'\b([\d,]{1,12}\.\d{2})\b')
    DATE_PATTERNS = [
        re.compile(r'(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2}\s*[AP]M)'),
        re.compile(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})'),
        re.compile(r'(\d{1,2}\s+\w+\s+\d{4})\s+(\d{1,2}:\d{2}\s*[AP]M)'),
    ]
    PHONE_PATTERN = re.compile(r'(?:\+254|0)([17]\d{8})')
    
    # Transaction type keywords
    TYPE_KEYWORDS = {
        TransactionType.SENT: ['sent to', 'transfer to', 'send money'],
        TransactionType.RECEIVED: ['received from', 'transfer from', 'you have received'],
        TransactionType.PAYBILL: ['paybill', 'pay bill', 'utility'],
        TransactionType.TILL: ['buy goods', 'till number', 'merchant payment'],
        TransactionType.AIRTIME: ['airtime', 'top up', 'topup'],
        TransactionType.WITHDRAWAL: ['withdraw', 'withdrawal', 'cash out', 'agent'],
        TransactionType.DEPOSIT: ['deposit', 'cash in'],
        TransactionType.REVERSAL: ['reversal', 'reversed'],
        TransactionType.FULIZA: ['fuliza'],
        TransactionType.LOAN: ['mshwari', 'kcb mpesa', 'loan', 'credit'],
        TransactionType.CHARGES: ['charge', 'fee', 'service fee'],
    }
    
    DATE_FORMATS = [
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d %B %Y %I:%M %p",
        "%d-%m-%Y %H:%M",
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def parse(self, text_content: str) -> ParsedStatement:
        """Main parsing entry point."""
        statement = ParsedStatement()
        
        if not text_content:
            statement.parsing_warnings.append("Empty content provided")
            return statement
        
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        statement.raw_lines_processed = len(lines)
        
        # Extract metadata
        statement.metadata = self._extract_metadata(text_content)
        
        # Detect and parse transaction format
        if self._is_tabular_format(text_content):
            statement.transactions = self._parse_tabular_format(lines, statement.parsing_warnings)
        else:
            statement.transactions = self._parse_text_format(lines, statement.parsing_warnings)
        
        # Post-process and validate
        statement.transactions = self._post_process(statement.transactions, statement.parsing_warnings)
        statement.metadata.transaction_count = len(statement.transactions)
        
        # Calculate totals
        self._calculate_totals(statement)
        
        self.logger.info(
            f"Parsed {len(statement.transactions)} transactions "
            f"with {len(statement.parsing_warnings)} warnings"
        )
        
        return statement
    
    def _extract_metadata(self, text: str) -> StatementMetadata:
        """Extract account metadata from statement header."""
        metadata = StatementMetadata()
        
        # Extract name (usually near top of statement)
        name_match = re.search(
            r'(?:Customer Name|Account Name|Name)\s*:?\s*([A-Z][A-Z\s]+[A-Z])',
            text, re.IGNORECASE
        )
        if name_match:
            metadata.account_name = name_match.group(1).strip().title()
        
        # Extract phone number
        phone_match = self.PHONE_PATTERN.search(text)
        if phone_match:
            metadata.phone_number = f"+254{phone_match.group(1)}"
        
        # Extract statement period
        period_match = re.search(
            r'(?:Statement Period|Period)\s*:?\s*'
            r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(?:to|-)?\s*'
            r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})',
            text, re.IGNORECASE
        )
        if period_match:
            try:
                metadata.statement_period_start = self._parse_date_flexible(period_match.group(1))
                metadata.statement_period_end = self._parse_date_flexible(period_match.group(2))
            except Exception:
                pass
        
        # Extract balances
        opening_match = re.search(
            r'(?:Opening Balance|Balance B/F)\s*:?\s*(?:Ksh\.?)?\s*([\d,]+\.?\d{0,2})',
            text, re.IGNORECASE
        )
        if opening_match:
            metadata.opening_balance = self._parse_amount(opening_match.group(1))
        
        closing_match = re.search(
            r'(?:Closing Balance|Balance C/F)\s*:?\s*(?:Ksh\.?)?\s*([\d,]+\.?\d{0,2})',
            text, re.IGNORECASE
        )
        if closing_match:
            metadata.closing_balance = self._parse_amount(closing_match.group(1))
        
        return metadata
    
    def _is_tabular_format(self, text: str) -> bool:
        """Detect if the PDF was extracted in tabular format."""
        # Tab-separated or pipe-separated indicates table extraction
        tab_lines = sum(1 for line in text.split('\n') if '\t' in line)
        return tab_lines > 5
    
    def _parse_tabular_format(
        self, 
        lines: List[str], 
        warnings: List[str]
    ) -> List[MPesaTransaction]:
        """Parse tab-separated table format from pdfplumber table extraction."""
        transactions = []
        header_found = False
        col_mapping = {}
        
        for line_num, line in enumerate(lines):
            if '\t' not in line:
                continue
            
            cols = [c.strip() for c in line.split('\t')]
            
            # Detect header row
            if not header_found:
                col_mapping = self._detect_columns(cols)
                if col_mapping:
                    header_found = True
                    continue
            
            if not header_found or len(cols) < 3:
                continue
            
            # Parse transaction row
            try:
                txn = self._parse_table_row(cols, col_mapping)
                if txn and txn.receipt_no:
                    transactions.append(txn)
            except Exception as e:
                warnings.append(f"Could not parse row {line_num}: {str(e)[:50]}")
        
        return transactions
    
    def _detect_columns(self, headers: List[str]) -> Dict[str, int]:
        """Map column names to indices."""
        mapping = {}
        header_map = {
            'receipt_no': ['receipt', 'receipt no', 'transaction id', 'ref'],
            'completion_time': ['completion time', 'date', 'time', 'datetime'],
            'description': ['description', 'details', 'narration'],
            'paid_in': ['paid in', 'credit', 'money in', 'received'],
            'withdrawn': ['withdrawn', 'debit', 'money out', 'sent'],
            'balance': ['balance', 'running balance', 'bal'],
        }
        
        for idx, header in enumerate(headers):
            header_lower = header.lower().strip()
            for field, keywords in header_map.items():
                if any(kw in header_lower for kw in keywords):
                    if field not in mapping:  # First match wins
                        mapping[field] = idx
        
        # Need at least receipt and one amount column
        has_required = 'receipt_no' in mapping or 'completion_time' in mapping
        return mapping if has_required else {}
    
    def _parse_table_row(
        self, 
        cols: List[str], 
        col_mapping: Dict[str, int]
    ) -> Optional[MPesaTransaction]:
        """Parse a single table row into a transaction."""
        def safe_get(field: str) -> str:
            idx = col_mapping.get(field)
            if idx is not None and idx < len(cols):
                return cols[idx].strip()
            return ""
        
        receipt = safe_get('receipt_no')
        
        # Validate receipt number format
        if receipt and not self.RECEIPT_PATTERN.match(receipt):
            # Try to find receipt in the full row
            row_text = ' '.join(cols)
            receipt_match = self.RECEIPT_PATTERN.search(row_text)
            receipt = receipt_match.group(1) if receipt_match else receipt
        
        if not receipt:
            return None
        
        txn = MPesaTransaction()
        txn.receipt_no = receipt
        
        # Parse datetime
        time_str = safe_get('completion_time')
        if time_str:
            txn.completion_time = self._parse_date_flexible(time_str)
        
        # Parse description
        txn.description = safe_get('description')
        
        # Parse amounts - handle comma-formatted numbers
        txn.paid_in = self._parse_amount(safe_get('paid_in'))
        txn.withdrawn = self._parse_amount(safe_get('withdrawn'))
        txn.balance = self._parse_amount(safe_get('balance'))
        
        # Classify transaction
        txn.transaction_type = self._classify_transaction(txn.description)
        txn.counterparty = self._extract_counterparty(txn.description)
        txn.reference = self._extract_reference(txn.description)
        
        return txn
    
    def _parse_text_format(
        self, 
        lines: List[str], 
        warnings: List[str]
    ) -> List[MPesaTransaction]:
        """Parse unstructured text format."""
        transactions = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Look for receipt number as transaction start
            receipt_match = self.RECEIPT_PATTERN.search(line)
            
            if receipt_match:
                # Collect context lines
                context_lines = [line]
                for j in range(1, 4):
                    if i + j < len(lines):
                        next_line = lines[i + j]
                        # Stop at next receipt number
                        if self.RECEIPT_PATTERN.search(next_line):
                            break
                        context_lines.append(next_line)
                
                try:
                    txn = self._parse_text_transaction(receipt_match.group(1), context_lines)
                    if txn:
                        transactions.append(txn)
                except Exception as e:
                    warnings.append(f"Parse error at line {i}: {str(e)[:50]}")
            
            i += 1
        
        return transactions
    
    def _parse_text_transaction(
        self, 
        receipt_no: str, 
        lines: List[str]
    ) -> Optional[MPesaTransaction]:
        """Parse transaction from text lines."""
        combined = ' '.join(lines)
        
        txn = MPesaTransaction()
        txn.receipt_no = receipt_no
        txn.description = combined[:200]  # Limit description length
        
        # Extract datetime
        for pattern in self.DATE_PATTERNS:
            date_match = pattern.search(combined)
            if date_match:
                date_str = f"{date_match.group(1)} {date_match.group(2)}"
                txn.completion_time = self._parse_date_flexible(date_str)
                if txn.completion_time:
                    break
        
        # Extract amounts - look for patterns like "Ksh 1,000.00"
        amounts = self.AMOUNT_PATTERN.findall(combined)
        parsed_amounts = [self._parse_amount(a) for a in amounts if self._parse_amount(a)]
        
        if not parsed_amounts:
            # Try plain amounts as fallback
            amounts = self.PLAIN_AMOUNT_PATTERN.findall(combined)
            parsed_amounts = [self._parse_amount(a) for a in amounts if self._parse_amount(a)]
        
        # Assign amounts based on context
        if 'received' in combined.lower() or 'paid in' in combined.lower():
            if parsed_amounts:
                txn.paid_in = parsed_amounts[0]
            if len(parsed_amounts) > 1:
                txn.balance = parsed_amounts[-1]
        else:
            if parsed_amounts:
                txn.withdrawn = parsed_amounts[0]
            if len(parsed_amounts) > 1:
                txn.balance = parsed_amounts[-1]
        
        txn.transaction_type = self._classify_transaction(combined)
        txn.counterparty = self._extract_counterparty(combined)
        
        return txn if txn.receipt_no else None
    
    def _classify_transaction(self, description: str) -> TransactionType:
        """Classify transaction type based on description keywords."""
        desc_lower = description.lower()
        
        for txn_type, keywords in self.TYPE_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                return txn_type
        
        return TransactionType.OTHER
    
    def _extract_counterparty(self, description: str) -> str:
        """Extract counterparty name/number from description."""
        patterns = [
            r'(?:to|from)\s+([A-Z][A-Z\s]+?)(?:\s+on|\s+via|\s+at|$)',
            r'(?:to|from)\s+(\+?254\d{9})',
            r'(?:to|from)\s+(0[17]\d{8})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:50]
        
        return ""
    
    def _extract_reference(self, description: str) -> str:
        """Extract business/paybill reference from description."""
        ref_match = re.search(
            r'(?:Account|Ref|Reference|A/C)\s*(?:No\.?)?\s*:?\s*(\w+)',
            description, re.IGNORECASE
        )
        return ref_match.group(1) if ref_match else ""
    
    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse amount string to Decimal, handling various formats."""
        if not amount_str:
            return None
        
        try:
            # Remove currency symbols and whitespace
            cleaned = re.sub(r'[Ksh\s]', '', str(amount_str))
            # Remove commas (thousand separators)
            cleaned = cleaned.replace(',', '')
            
            if not cleaned or cleaned == '-':
                return None
            
            value = Decimal(cleaned)
            return value if value >= 0 else None
            
        except InvalidOperation:
            return None
    
    def _parse_date_flexible(self, date_str: str) -> Optional[datetime]:
        """Try multiple date formats for flexible parsing."""
        if not date_str:
            return None
        
        # Normalize AM/PM
        normalized = re.sub(r'\s+', ' ', date_str.strip())
        normalized = re.sub(r'(\d)(AM|PM)', r'\1 \2', normalized, flags=re.IGNORECASE)
        
        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        
        # Try dateutil as last resort
        try:
            from dateutil import parser as dateutil_parser
            return dateutil_parser.parse(normalized, dayfirst=True)
        except Exception:
            return None
    
    def _post_process(
        self, 
        transactions: List[MPesaTransaction],
        warnings: List[str]
    ) -> List[MPesaTransaction]:
        """Validate and clean parsed transactions."""
        valid = []
        seen_receipts = set()
        
        for txn in transactions:
            # Remove duplicates
            if txn.receipt_no in seen_receipts:
                warnings.append(f"Duplicate receipt {txn.receipt_no} removed")
                continue
            
            seen_receipts.add(txn.receipt_no)
            
            # Ensure at least one amount
            if txn.paid_in is None and txn.withdrawn is None:
                warnings.append(f"Transaction {txn.receipt_no} has no amount data")
                # Keep it but mark it
                txn.description = f"[Amount unclear] {txn.description}"
            
            valid.append(txn)
        
        # Sort by date
        valid.sort(key=lambda t: t.completion_time or datetime.min)
        
        return valid
    
    def _calculate_totals(self, statement: ParsedStatement) -> None:
        """Calculate summary totals from transactions."""
        total_in = Decimal('0')
        total_out = Decimal('0')
        
        for txn in statement.transactions:
            if txn.paid_in:
                total_in += txn.paid_in
            if txn.withdrawn:
                total_out += txn.withdrawn
        
        statement.metadata.total_paid_in = total_in
        statement.metadata.total_withdrawn = total_out