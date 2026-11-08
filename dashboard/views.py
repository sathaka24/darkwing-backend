from django.http import JsonResponse
from django.views import View
from django.db.models import Sum, Count
from django.utils import timezone

from invoices.models import Invoice, Payment


class DashboardStatsView(View):

    # GET /api/dashboard/stats/
    #
    # The home-screen widgets: this month's income (summed from
    # payment.paid_at, NOT invoice dates) plus the four status counts.
    # Read-only — this app writes nothing.

    def get(self, request):

        # work out the current month's window in local (Colombo) time,
        # so the boundary lands on Colombo midnight, not UTC's.
        today = timezone.localdate()
        year = today.year
        month = today.month

        # It sums payments, not invoices. Income is about money that actually arrived, so it looks at the payment rows and their paid_at timestamp — not at invoice dates.
        income_result = Payment.objects.filter(
            paid_at__year=year,
            paid_at__month=month,
        ).aggregate(total=Sum('amount'))

        # aggregate returns {'total': None} when there are no rows
        monthly_income = income_result['total'] or 0

        # --- status counts: one grouped query, not four ---
        # group invoices by status and count each bucket
        status_rows = (
            Invoice.objects
            .values('status')
            .annotate(count=Count('id'))
        )

        # above returns somthing like this -> [ {status: 'ISSUED', count: 12}, {status: 'PAID', count: 8}, {status: 'CANCELLED', count: 2} ]
        

        # turn the rows into a quick lookup {status: count}
        counts_by_status = {row['status']: row['count'] for row in status_rows}

        # build the widget payload. "pending" = has a balance left, which
        # in our status model is PARTIALLY_PAID.
        counts = {
            'issued': counts_by_status.get('ISSUED', 0),
            'pending_balance': counts_by_status.get('PARTIALLY_PAID', 0),
            'paid': counts_by_status.get('PAID', 0),
            'cancelled': counts_by_status.get('CANCELLED', 0),
        }

        return JsonResponse({
            'monthly_income': str(monthly_income),   # string keeps exact decimals
            'month': month,
            'year': year,
            'counts': counts,
        })


class MonthlyReportView(View):

    # GET /api/dashboard/monthly-report/?year=&month=
    #
    # The full month as a flat array, ready for the frontend engine
    # to turn into XLSX or PDF. Year and month arrive as query params.
    # Read-only.

    def get(self, request):

        # --- read & validate the query params ---
        # default to the current month if either is missing
        today = timezone.localdate()

        try:
            year = int(request.GET.get('year', today.year))
            month = int(request.GET.get('month', today.month))
        except ValueError:
            return JsonResponse({'error': 'year and month must be numbers'}, status=400)

        if month < 1 or month > 12:
            return JsonResponse({'error': 'month must be between 1 and 12'}, status=400)

        # --- pull every invoice issued in that month ---
        # select_related pulls customer + created_by in the same query,
        # so we don't fire a DB hit per row.
        invoices = (
            Invoice.objects
            .select_related('customer', 'created_by')
            .filter(issue_date__year=year, issue_date__month=month)
            .order_by('issue_date', 'id')
        )

        # --- flatten each invoice into one report row ---
        rows = []
        total_billed = 0
        total_collected = 0

        for inv in invoices:
            # amount_paid is a live @property summing this invoice's payments
            billed = inv.grand_total
            collected = inv.amount_paid

            # don't count cancelled invoices toward the money totals
            if inv.status != 'CANCELLED':
                total_billed += billed
                total_collected += collected

            rows.append({
                'invoice_number': inv.invoice_number,
                'issue_date': inv.issue_date.isoformat(),
                'customer_name': inv.customer.name,
                'customer_code': inv.customer.customer_code,
                'created_by': inv.created_by.get_full_name() or inv.created_by.username,
                'status': inv.status,
                'grand_total': str(billed),
                'amount_paid': str(collected),
                'balance_due': str(inv.balance_due),
            })

        return JsonResponse({
            'year': year,
            'month': month,
            'count': len(rows),
            'total_billed': str(total_billed),
            'total_collected': str(total_collected),
            'invoices': rows,
        })
