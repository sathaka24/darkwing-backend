import json
from django.http import JsonResponse
from django.views import View
from django.db.models import Q
from .models import Customer


# small helper so list and detail return the same shape
def customer_to_dict(customer):
    return {
        'id': customer.id,
        'customer_code': customer.customer_code,
        'name': customer.name,
        'mobile': customer.mobile,
        'email': customer.email,
        'notes': customer.notes,
        'created_at': customer.created_at.isoformat(),
        'updated_at': customer.updated_at.isoformat(),
    }


class CustomerListCreateView(View):

    # GET  /api/customers/?search=
    # POST /api/customers/
    #
    # One class, two methods. Django routes on the HTTP method,
    # so the same URL serves both the list and the create.

    def get(self, request):

        # List every customer, newest first.
        # The ?search= query string is optional. It's not part of
        # the URL pattern — the view reads it straight off request.GET.

        # here it reads the values of ?search=
        search = request.GET.get('search', '')

        customers = Customer.objects.all()

        # if a search term was given, filter by name OR code OR mobile
        if search:
            customers = customers.filter(
                Q(name__icontains=search) |
                Q(customer_code__icontains=search) |
                Q(mobile__icontains=search)
            )

        customers = customers.order_by('-created_at')

        # build the list of dicts to send back
        data = [customer_to_dict(c) for c in customers]

        return JsonResponse({'customers': data})

    def post(self, request):

        # Body: {"name", "mobile", "email"?, "notes"?, "force"?}
        # "force": true   → skip the duplicate check and create anyway

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        name = data.get('name', '')
        mobile = data.get('mobile', '')
        email = data.get('email', '')
        force = data.get('force', False)   # frontend sets this after the user confirms

        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        if not mobile:
            return JsonResponse({'error': 'Mobile is required'}, status=400)

        # --- duplicate check (only when not forced) ---
        if not force:

            # look for an existing customer with the same mobile or email
            existing = Customer.objects.filter(mobile=mobile).first()

            # only check email if one was actually given
            if existing is None and email:
                existing = Customer.objects.filter(email=email).first()

            if existing is not None:
                # 409 Conflict — tell the frontend WHO matched and WHY,
                # so it can show "Customer already exists, use them or create new?"
                return JsonResponse(
                    {
                        'error': 'duplicate',
                        'message': 'A customer with this mobile or email already exists.',
                        'existing_customer': customer_to_dict(existing),
                    },
                    status=409
                )

        # --- create (either no duplicate, or force=true) ---
        customer = Customer.objects.create(
            name=name,
            mobile=mobile,
            email=email or None,   # store None (not '') so blank emails don't collide
            notes=data.get('notes', ''),
        )

        return JsonResponse(customer_to_dict(customer), status=201)


class CustomerDetailView(View):

    # GET   /api/customers/<int:pk>/
    # PATCH /api/customers/<int:pk>/
    #
    # A single customer record. pk is captured from the URL by
    # <int:pk> and passed in as a keyword argument.

    def get(self, request, pk):

        # Return one customer's full record.
        try:
            customer = Customer.objects.get(id=pk)
        except Customer.DoesNotExist:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        return JsonResponse(customer_to_dict(customer))

    def patch(self, request, pk):

        # Partial update — the frontend sends only the fields that changed.
        # Customers are editable (unlike invoices, which are frozen).

        try:
            customer = Customer.objects.get(id=pk)
        except Customer.DoesNotExist:
            return JsonResponse({'error': 'Customer not found'}, status=404)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # only touch a field if it was actually sent in the body.
        # customer_code is never editable — it's system-assigned.
        if 'name' in data:
            customer.name = data['name']

        if 'mobile' in data:
            customer.mobile = data['mobile']

        if 'email' in data:
            customer.email = data['email']

        if 'notes' in data:
            customer.notes = data['notes']

        customer.save()  # updated_at refreshes via auto_now

        return JsonResponse(customer_to_dict(customer))

