from django.db import models, transaction

# Create your models here.

class Customer(models.Model):

    # The customer directory. Details are saved once and reused when building
    # invoices. Each customer gets an auto-generated, human-facing code
    # (CUST-001, CUST-002, ...) alongside the numeric primary key.

    # Human-facing ID, e.g. "CUST-001". Generated server-side on first save.
    customer_code = models.CharField(max_length=12, unique=True, db_index=True, editable=False)

    name = models.CharField(max_length=150)
    mobile = models.CharField(max_length=20)
    email = models.EmailField(max_length=254, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # here we define the Meta class. this is a Django's inner class. 

    class Meta:
        db_table = "customer"                   # this name the table related to this model as "customer"
        ordering = ["name"]                     # this is the default sorting order. when call the Customer.objects.all() the data comes under this filed sort

        # here we tells the database to build lookup indexes on name and mobile. The schema says customers are searchable by name and mobile
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["mobile"]),
        ]

    # this magic function we use to print our Customer object. it is easy for debug also
    def __str__(self):
        return f"{self.customer_code} . {self.name}"

    # this is inherited func from model class. here we override the function. 
    # cuz if a customer don't have a code yet. then here it generate code and save to database
    def save(self, *args, **kwargs):

        if not self.customer_code:

            self.customer_code = self._generate_code()

        super().save(*args, **kwargs)


    @staticmethod
    def _generate_code():

        # Produce the next sequential code (CUST-001) under a row lock so two
        # concurrent registrations can't collide on the same number.

        with transaction.atomic():

            last = (

                Customer.objects.select_for_update()  # locks the rows it reads until the transaction finishes. This is the concurrency guard
                .order_by("-id")                      # gets the rows ordered by ids
                .first()                              # gets the most recent customer (highest id)
            )

            next_no = (last.id + 1) if last else 1

            return f"CUST-{next_no:03d}"   # here we use 03d to represnt the number with 3 digits -> 001, 042



            

    
