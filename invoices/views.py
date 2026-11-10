import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.views import View
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Invoice, InvoiceItem, Payment, InvoiceCounter, CompanyConfig
from customers.models import Customer

# To disable the CRFS token checking. cuz we proviod our own token 
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


# ---------------------------------------------------------------------------
# helper — turn one Invoice (with its items, payments, computed flags)
# into the dict the frontend / document engine expects.
# money is sent as strings to keep the exact decimal precision.
# ---------------------------------------------------------------------------
def invoice_to_dict(invoice, full=False):

    data = {
        'id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'customer': {
            'id': invoice.customer.id,
            'customer_code': invoice.customer.customer_code,
            'name': invoice.customer.name,
            'mobile': invoice.customer.mobile,
        },
        'created_by': invoice.created_by.get_full_name() or invoice.created_by.username,
        'status': invoice.status,
        'issue_date': invoice.issue_date.isoformat(),
        'warranty_stamp': invoice.warranty_stamp,
        'grand_total': str(invoice.grand_total),

        # live @property values, computed from the frozen rows + payments
        'amount_paid': str(invoice.amount_paid),
        'balance_due': str(invoice.balance_due),
    }

    # the detail view needs the whole picture; the list view stays lean
    if full:
        data['notes'] = invoice.notes
        data['cancelled_at'] = invoice.cancelled_at.isoformat() if invoice.cancelled_at else None

        data['items'] = [
            {
                'position': item.position,
                'description': item.description,
                'model': item.model,
                'part_number': item.part_number,
                'brand': item.brand,
                'quantity': str(item.quantity),
                'unit_price': str(item.unit_price),
                'discount_percent': str(item.discount_percent),
                'has_warranty': item.has_warranty,
                'line_total': str(item.line_total),
            }
            for item in invoice.items.all().order_by('position')
        ]

        data['payments'] = [
            {
                'kind': p.kind,
                'amount': str(p.amount),
                'paid_at': p.paid_at.isoformat(),
            }
            for p in invoice.payments.all().order_by('paid_at')
        ]

        # the flags the PDF engine renders on
        data['show_paid_stamp'] = invoice.show_paid_stamp
        data['paid_date'] = invoice.paid_date.isoformat() if invoice.paid_date else None
        data['show_warranty_stamp'] = invoice.show_warranty_stamp
        data['show_term_4'] = invoice.show_term_4

        cfg = invoice.company_config
        data['company'] = {
            'email': cfg.company_email,
            'phone': cfg.company_phone,
            'terms_and_conditions': cfg.terms_and_conditions,
            'bank_details': cfg.bank_details,
        }
        data['customer_snapshot'] = {
            'name': invoice.customer_name,
            'mobile': invoice.customer_mobile,
        }

    return data


# ---------------------------------------------------------------------------
# small helper to safely turn a value into Decimal
# ---------------------------------------------------------------------------
def to_decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{field_name} is not a valid number')


@method_decorator(csrf_exempt, name='dispatch')
class InvoiceListCreateView(View):

    # GET  /api/invoices/?status=&search=
    # POST /api/invoices/
    #
    # List the tracking table, or create a brand-new invoice.

    def get(self, request):

        # The filterable list behind the All Invoices tab.
        # ?status= buckets the tracking table, ?search= matches
        # invoice number or customer name.
        status = request.GET.get('status', '')
        search = request.GET.get('search', '')

        invoices = Invoice.objects.select_related('customer', 'created_by', 'company_config')

        if status:
            invoices = invoices.filter(status=status)

        if search:
            invoices = invoices.filter(
                Q(invoice_number__icontains=search) |
                Q(customer__name__icontains=search)
            )

        invoices = invoices.order_by('-id')

        data = [invoice_to_dict(inv) for inv in invoices]
        return JsonResponse({'invoices': data})

    def post(self, request):

        # Create the invoice + its items + any advance, all in ONE
        # transaction. The number, line totals and grand total are
        # computed here on the server and frozen.
        # Body: {customer, series, warranty_stamp?, notes?,
        #        items: [...], advance?: {amount, paid_at?}}

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        customer_id = data.get('customer')
        series = data.get('series', '')
        items = data.get('items', [])

        # ---- validate the basics before we touch the database ----
        if not customer_id:
            return JsonResponse({'error': 'Customer is required'}, status=400)

        if series not in ('H', 'E'):
            return JsonResponse({'error': 'Series must be H or E'}, status=400)

        if not items:
            return JsonResponse({'error': 'At least one item is required'}, status=400)

        # customer must exist
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        config = CompanyConfig.current()
        if config is None:
            return JsonResponse({'error': 'Company config not set up'}, status=400)
        # ---- everything below runs atomically ----
        # if anything raises, the whole invoice (and its number) rolls back,
        # so the counter never leaves a gap.
        try:
            with transaction.atomic():

                # ask the counter for the next gap-free number (locks the row)
                year = timezone.localdate().year
                number = InvoiceCounter.next_number(series, year)
                
                # create the header first with a placeholder total of 0;
                # we fill grand_total once the items are summed.

                invoice = Invoice.objects.create(
                    invoice_number=number,
                    customer=customer,
                    created_by=request.user,
                    status=Invoice.Status.ISSUED,
                    warranty_stamp=data.get('warranty_stamp', 'NONE'),
                    notes=data.get('notes', ''),
                    grand_total=Decimal('0.00'),
                    company_config=config,                        # ← pointer only
                    customer_name=customer.name,
                    customer_mobile=customer.mobile,
                    signed_by_id=data.get('signed_by'),
                    signature_image=data.get('signature_image', ''),
                )

                # build each line item, let the model freeze its line_total,
                # and accumulate the grand total as we go.
                grand_total = Decimal('0.00')

                for index, raw in enumerate(items):
                    item = InvoiceItem(
                        invoice=invoice,
                        position=index,
                        description=raw.get('description', ''),
                        model=raw.get('model', ''),
                        part_number=raw.get('part_number', ''),
                        brand=raw.get('brand', ''),
                        quantity=to_decimal(raw.get('quantity', 0), 'quantity'),
                        unit_price=to_decimal(raw.get('unit_price', 0), 'unit_price'),
                        discount_percent=to_decimal(raw.get('discount_percent', 0), 'discount_percent'),
                        has_warranty=raw.get('has_warranty', False),
                    )
                    item.line_total = item.compute_line_total()   # freeze it
                    item.save()
                    grand_total += item.line_total

                # now stamp the frozen grand total on the header
                invoice.grand_total = grand_total

                # ---- optional advance payment ----
                advance = data.get('advance')
                if advance:
                    amount = to_decimal(advance.get('amount', 0), 'advance amount')

                    if amount > 0:
                        Payment.objects.create(
                            invoice=invoice,
                            kind=Payment.Kind.ADVANCE,
                            amount=amount,
                            paid_at=advance.get('paid_at') or timezone.now(),
                            recorded_by=request.user,
                        )
                        # a partial payment moves it out of plain ISSUED
                        if amount < grand_total:
                            invoice.status = Invoice.Status.PARTIALLY_PAID
                        else:
                            invoice.status = Invoice.Status.PAID

                invoice.save()

        except ValueError as e:
            # bad number somewhere in the items / advance → clean 400,
            # and the atomic block already rolled everything back.
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse(invoice_to_dict(invoice, full=True), status=201)

class InvoiceDetailView(View):

    # GET /api/invoices/<int:pk>/
    #
    # Everything the document engine needs in one call: header,
    # items, payments, and the computed render flags.

    def get(self, request, pk):
        try:
            invoice = Invoice.objects.select_related('customer', 'created_by').get(id=pk)
        except Invoice.DoesNotExist:
            return JsonResponse({'error': 'Invoice not found'}, status=404)

        return JsonResponse(invoice_to_dict(invoice, full=True))


@method_decorator(csrf_exempt, name='dispatch')
class PaymentCreateView(View):

    # POST /api/invoices/<int:pk>/payments/
    #
    # Append ONE payment row (advance or balance) with its own
    # timestamp. The invoice body is never touched — money is rows,
    # not fields. Recomputes status from the running balance.

    def post(self, request, pk):
        try:
            invoice = Invoice.objects.get(id=pk)
        except Invoice.DoesNotExist:
            return JsonResponse({'error': 'Invoice not found'}, status=404)

        # can't collect money on a cancelled invoice
        if invoice.status == Invoice.Status.CANCELLED:
            return JsonResponse({'error': 'Invoice is cancelled'}, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        kind = data.get('kind', '')
        if kind not in ('ADVANCE', 'BALANCE'):
            return JsonResponse({'error': 'kind must be ADVANCE or BALANCE'}, status=400)

        try:
            amount = to_decimal(data.get('amount', 0), 'amount')
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        if amount <= 0:
            return JsonResponse({'error': 'amount must be greater than zero'}, status=400)

        with transaction.atomic():
            Payment.objects.create(
                invoice=invoice,
                kind=kind,
                amount=amount,
                paid_at=data.get('paid_at') or timezone.now(),
                recorded_by=request.user,
            )

            # re-derive status from the live balance
            if invoice.balance_due <= 0:
                invoice.status = Invoice.Status.PAID
            else:
                invoice.status = Invoice.Status.PARTIALLY_PAID
            invoice.save()

        return JsonResponse(invoice_to_dict(invoice, full=True), status=201)


@method_decorator(csrf_exempt, name='dispatch')
class InvoiceMarkPaidView(View):

    # POST /api/invoices/<int:pk>/mark-paid/
    #
    # One click clears whatever balance is left: writes a BALANCE
    # payment for the remainder and flips status to PAID. That
    # payment's timestamp becomes the date on the red PAID stamp.
    # Body: none (or {paid_at})

    def post(self, request, pk):
        try:
            invoice = Invoice.objects.get(id=pk)
        except Invoice.DoesNotExist:
            return JsonResponse({'error': 'Invoice not found'}, status=404)

        if invoice.status == Invoice.Status.CANCELLED:
            return JsonResponse({'error': 'Invoice is cancelled'}, status=400)

        if invoice.status == Invoice.Status.PAID:
            return JsonResponse({'error': 'Invoice is already paid'}, status=400)

        # body is optional here — allow a backdated paid_at if sent
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        remaining = invoice.balance_due

        with transaction.atomic():
            # only write a row if there's actually something left to clear
            if remaining > 0:
                Payment.objects.create(
                    invoice=invoice,
                    kind=Payment.Kind.BALANCE,
                    amount=remaining,
                    paid_at=data.get('paid_at') or timezone.now(),
                    recorded_by=request.user,
                )

            invoice.status = Invoice.Status.PAID
            invoice.save()

        return JsonResponse(invoice_to_dict(invoice, full=True))

@method_decorator(csrf_exempt, name='dispatch')
class InvoiceCancelView(View):

    # POST /api/invoices/<int:pk>/cancel/
    #
    # Sets status to CANCELLED and records cancelled_at. The row
    # stays in the database — the invoice number is spent, never reused.
    # Body: none (or {reason})

    def post(self, request, pk):
        try:
            invoice = Invoice.objects.get(id=pk)
        except Invoice.DoesNotExist:
            return JsonResponse({'error': 'Invoice not found'}, status=404)

        if invoice.status == Invoice.Status.CANCELLED:
            return JsonResponse({'error': 'Invoice is already cancelled'}, status=400)

        # reason is optional; if sent, tuck it into notes
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        reason = data.get('reason', '')

        invoice.status = Invoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        if reason:
            invoice.notes = (invoice.notes + f'\nCancelled: {reason}').strip()
        invoice.save()

        return JsonResponse(invoice_to_dict(invoice, full=True))

@method_decorator(csrf_exempt, name='dispatch')
class CompanyConfigView(View):

    # GET  /api/company-config/   → the current config
    # POST /api/company-config/   → publish new details (dedups automatically)

    def get(self, request):
        cfg = CompanyConfig.current()
        if cfg is None:
            return JsonResponse({'error': 'Company config not set up'}, status=404)
        return JsonResponse({
            'id': cfg.id,
            'company_email': cfg.company_email,
            'company_phone': cfg.company_phone,
            'terms_and_conditions': cfg.terms_and_conditions,
            'bank_details': cfg.bank_details,
        })

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        cfg = CompanyConfig.get_or_publish(
            company_email=data.get('company_email', ''),
            company_phone=data.get('company_phone', ''),
            terms_and_conditions=data.get('terms_and_conditions', []),
            bank_details=data.get('bank_details', {}),
        )
        return JsonResponse({'id': cfg.id, 'is_current': cfg.is_current}, status=200)