from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

import hashlib, json
from django.db import transaction

# Create your models here.

# ---------------------------------------------------------------------------
# Gap-free numbering
# ---------------------------------------------------------------------------
class InvoiceCounter(models.Model):
    
    # One row per year holding the last invoice number issued. Numbers are
    # handed out inside a transaction with the row locked (select_for_update),
    # so two concurrent issues can neither collide nor skip a number.

    # Schema rule #05: numbering must be sequential and gap-free.
    

    year = models.PositiveIntegerField(primary_key=True)
    last_no = models.PositiveIntegerField(default=0)

    # setting the table name
    class Meta:
        db_table = "invoice_counter"

    # for printing. defining the printing format
    def __str__(self):
        return f"{self.year} → {self.last_no}"


    SERIES = ("H", "E")

    # Here @classmethod means the method automatically receives the class itself as its first argument, named cls
    @classmethod
    def next_number(cls, series, year=None):
        series = series.upper()
        if series not in cls.SERIES:
            raise ValueError(f"series must be one of {cls.SERIES}, got {series!r}")
        year = year or timezone.localdate().year

        # below line locks the rows so other threads can't update the table. get_or_create() func check whether any raw is in the table for given year
        # if raws exsists for given year it return a tuple which contain all the raws in that year. if there is no any raw it return with last_no = 0
        counter, _ = cls.objects.select_for_update().get_or_create(year=year)

        counter.last_no += 1
        counter.save(update_fields=["last_no"])
        return f"DWM{year}{series}{counter.last_no:04d}"


# ---------------------------------------------------------------------------
# Invoice header
# ---------------------------------------------------------------------------
class Invoice(models.Model):
    
    # The invoice header. Totals and the invoice number are computed server-side
    # and frozen once the invoice is issued — the record is never recomputed on
    # read. Corrections are a new invoice or a cancellation, never an edit.

    # It also snapshots the parts of the printed document that live in global
    # config — terms & conditions, bank details — and who signed it, so an old
    # invoice always reprints exactly as issued even if those later change.

    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    class Warranty(models.TextChoices):
        # 1–12 months → the 12 warranty stamps. CHECKING = warranty lasts only
        # until the part is fixed and verified working. APPROVED = invoice-level
        # roll-up for an invoice whose items carry different warranties (used on
        # the invoice stamp only — never on a single item).
        NONE = "NONE", "None"
        ONE_MONTH = "ONE_MONTH", "1 month"
        TWO_MONTHS = "TWO_MONTHS", "2 months"
        THREE_MONTHS = "THREE_MONTHS", "3 months"
        FOUR_MONTHS = "FOUR_MONTHS", "4 months"
        FIVE_MONTHS = "FIVE_MONTHS", "5 months"
        SIX_MONTHS = "SIX_MONTHS", "6 months"
        SEVEN_MONTHS = "SEVEN_MONTHS", "7 months"
        EIGHT_MONTHS = "EIGHT_MONTHS", "8 months"
        NINE_MONTHS = "NINE_MONTHS", "9 months"
        TEN_MONTHS = "TEN_MONTHS", "10 months"
        ELEVEN_MONTHS = "ELEVEN_MONTHS", "11 months"
        TWELVE_MONTHS = "TWELVE_MONTHS", "12 months"
        CHECKING = "CHECKING", "Checking"
        APPROVED = "APPROVED", "Approved"

    invoice_number = models.CharField(
        max_length=20, unique=True, db_index=True, editable=False
    )

    # here we define the foreign keys
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,      # never delete a customer out from under an invoice
        related_name="invoices",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices_created",
    )

    # Who signed/approved the issued document, chosen on the frontend. NULL is
    # a real, stored state — it means the invoice was issued *unsigned* (blank
    # signature line), not that data is missing. Distinct from created_by,
    # which is who built the record.
    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices_signed",
    )

    # The signer's signature as printed, snapshotted per invoice (a base64
    # data URL, e.g. "data:image/png;base64,..."). Stored on the row rather
    # than referenced from the user so that (a) changing a user's signature
    # never alters past invoices, and (b) it survives a host's ephemeral
    # filesystem (e.g. Railway), unlike a media file. Blank = issued unsigned,
    # matching signed_by = NULL.
    signature_image = models.TextField(blank=True)

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ISSUED,
        db_index=True,
    )

    issue_date = models.DateField(default=timezone.localdate)
    warranty_stamp = models.CharField(
        max_length=16, choices=Warranty.choices, default=Warranty.NONE
    )

    company_config = models.ForeignKey(
    'CompanyConfig', on_delete=models.PROTECT, related_name='invoices',
    )

    # Frozen at issue: Σ of line totals. Never recomputed on read.
    grand_total = models.DecimalField(max_digits=12, decimal_places=2)

    # --- Frozen document snapshot ---------------------------------------
    # Copied from the live data at issue so the invoice reprints exactly as
    # issued, even if the customer, company contact, terms or bank details
    # change later. The frontend document engine renders straight from these.
    #
    # Customer identity as printed on the "INVOICE FOR" line. The `customer`
    # FK is kept for linking/filtering, but the PDF uses these frozen copies:
    customer_name = models.CharField(max_length=150, blank=True)
    customer_mobile = models.CharField(max_length=20, blank=True)


    notes = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoice"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["issue_date"]),
        ]

    def __str__(self):
        return self.invoice_number


    # every row in invoice table is like instances of Invoice class right. when on anywhere we get a row it is a class of Invoice. 
    # when we call like balance_due every time it get grand total and reduce amount_paid and give us the values instead of recording everything
    
    @property
    def amount_paid(self):
        total = self.payments.aggregate(s=Sum("amount"))["s"]
        return total or Decimal("0.00")

    @property
    def advance_paid(self):
        total = self.payments.filter(kind=Payment.Kind.ADVANCE).aggregate(
            s=Sum("amount")
        )["s"]
        return total or Decimal("0.00")

    @property
    def balance_due(self):
        return self.grand_total - self.amount_paid

    @property
    def show_paid_stamp(self):
        return self.status == self.Status.PAID

    @property
    def paid_date(self):
        """Timestamp of the balance payment that cleared the invoice."""
        last_balance = (
            self.payments.filter(kind=Payment.Kind.BALANCE)
            .order_by("-paid_at")
            .first()
        )
        return last_balance.paid_at if last_balance else None

    @property
    def show_warranty_stamp(self):
        return self.warranty_stamp != self.Warranty.NONE

    @property
    def show_term_4(self):
        """Terms & Conditions rule #4 prints when any item carries warranty."""
        return self.items.filter(has_warranty=True).exists()


# ---------------------------------------------------------------------------
# Line items
# ---------------------------------------------------------------------------
class InvoiceItem(models.Model):
    
    # One row per item on an invoice. Discount is applied item-wise. Rows are
    # frozen together with their invoice and cascade-delete with it.
    

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="items"
    )

    position = models.PositiveIntegerField(default=0)  # keeps PDF ordering
    description = models.CharField(max_length=255)
    model = models.CharField(max_length=100, blank=True)
    part_number = models.CharField(max_length=100, blank=True)
    brand = models.CharField(max_length=100, blank=True)

    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    # has_warranty = models.BooleanField(default=False)

    warranty = models.CharField(
        max_length=16,
        choices=Invoice.Warranty.choices,   # same full list as the invoice
        default=Invoice.Warranty.NONE,
    )

    # Frozen at issue: (qty * unit_price) - discount.
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "invoice_item"
        ordering = ["invoice", "position"]
        indexes = [
            models.Index(fields=["invoice"]),
        ]

    def __str__(self):
        return f"{self.invoice_id} · {self.description}"

    def compute_line_total(self):
        """
        Helper the create path uses before freezing. Not called on read —
        line_total is the stored, frozen source of truth once issued.
        """
        gross = self.quantity * self.unit_price
        discount = gross * (self.discount_percent / Decimal("100"))
        return (gross - discount).quantize(Decimal("0.01"))


class CompanyConfig(models.Model):

    # One row per DISTINCT set of company details. Re-entering the same
    # details reuses the row; only changed details create a new one.
    # Rows are never edited, so invoices can safely point at them.

    company_email = models.EmailField(max_length=254, blank=True)
    company_phone = models.CharField(max_length=20, blank=True)
    terms_and_conditions = models.JSONField(default=list)
    bank_details = models.JSONField(default=dict)

    content_hash = models.CharField(max_length=64, unique=True, editable=False)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def _hash(company_email, company_phone, terms_and_conditions, bank_details):
        blob = json.dumps(
            {'e': company_email, 'p': company_phone,
             't': terms_and_conditions, 'b': bank_details},
            sort_keys=True, separators=(',', ':'),
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first()

    @classmethod
    def get_or_publish(cls, *, company_email, company_phone,
                       terms_and_conditions, bank_details):
        h = cls._hash(company_email, company_phone, terms_and_conditions, bank_details)
        with transaction.atomic():
            version = cls.objects.filter(content_hash=h).first()
            if version is None:
                version = cls.objects.create(
                    company_email=company_email,
                    company_phone=company_phone,
                    terms_and_conditions=terms_and_conditions,
                    bank_details=bank_details,
                    content_hash=h,
                )
            cls.objects.exclude(pk=version.pk).filter(is_current=True).update(is_current=False)
            if not version.is_current:
                version.is_current = True
                version.save(update_fields=['is_current'])
            return version

        

# ---------------------------------------------------------------------------
# Payments (append-only)
# ---------------------------------------------------------------------------
class Payment(models.Model):
    
    # One row per money event. An advance and a balance are two rows, each with
    # its own timestamp. Recording a payment appends a row and flips the
    # invoice status — the invoice body itself is never mutated.
    

    class Kind(models.TextChoices):
        ADVANCE = "ADVANCE", "Advance"
        BALANCE = "BALANCE", "Balance"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payments"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(default=timezone.now, db_index=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment"
        ordering = ["paid_at"]
        indexes = [
            models.Index(fields=["invoice"]),
            models.Index(fields=["paid_at"]),
        ]

    def __str__(self):
        return f"{self.invoice_id} · {self.kind} · {self.amount}"