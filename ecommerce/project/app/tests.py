from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase
from .models import Order, Product
from .utils import generate_token


class UserApiTests(APITestCase):
    def test_admin_can_list_users(self):
        admin = User.objects.create_user(
            username="admin",
            password="test-password",
            is_staff=True,
        )
        user = User.objects.create_user(
            username="customer@example.com",
            email="customer@example.com",
            first_name="Customer",
            password="test-password",
        )
        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/users/getallusers/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        listed_user = next(item for item in response.data if item["id"] == user.id)
        self.assertEqual(listed_user["name"], "Customer")
        self.assertEqual(listed_user["email"], "customer@example.com")

    def test_registration_creates_active_user_that_can_log_in(self):
        response = self.client.post(
            "/api/users/register",
            {
                "fname": "Test",
                "lname": "User",
                "email": "test@example.com",
                "password": "test-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="test@example.com")
        self.assertTrue(user.is_active)

        login_response = self.client.post(
            "/api/users/login",
            {"email": "test@example.com", "password": "test-password"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("access", login_response.data)
        self.assertEqual(login_response.data["firstName"], "Test")
        self.assertEqual(login_response.data["lastName"], "User")

    def test_login_accepts_email(self):
        User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="test-password",
        )

        response = self.client.post(
            "/api/users/login",
            {"email": "test@example.com", "password": "test-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["firstName"], "")
        self.assertEqual(response.data["lastName"], "")

    def test_login_accepts_admin_username(self):
        User.objects.create_user(
            username="storeadmin",
            email="admin@example.com",
            password="test-password",
            is_staff=True,
        )

        response = self.client.post(
            "/api/users/login",
            {"email": "storeadmin", "password": "test-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["isAdmin"])

    def test_authenticated_user_can_update_profile_and_password(self):
        user = User.objects.create_user(
            username="customer@example.com",
            email="customer@example.com",
            first_name="Old",
            last_name="Name",
            password="old-password",
        )
        self.client.force_authenticate(user=user)

        response = self.client.put(
            "/api/users/profile/",
            {
                "fname": "Updated",
                "lname": "Customer",
                "password": "new-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["firstName"], "Updated")
        self.assertEqual(response.data["lastName"], "Customer")
        user.refresh_from_db()
        self.assertTrue(user.check_password("new-password"))

    def test_profile_update_requires_authentication(self):
        response = self.client.put(
            "/api/users/profile/",
            {"fname": "Updated", "lname": "Customer"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_activation_activates_user(self):
        user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="test-password",
            is_active=False,
        )
        response = self.client.get(
            reverse(
                "activate",
                kwargs={
                    "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": generate_token.make_token(user),
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)


class OrderApiTests(APITestCase):
    def test_customer_can_only_list_their_own_orders(self):
        user = User.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="test-password",
        )
        another_user = User.objects.create_user(
            username="another@example.com",
            email="another@example.com",
            password="test-password",
        )
        own_order = Order.objects.create(user=user, totalPrice="25.00")
        Order.objects.create(user=another_user, totalPrice="50.00")
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/orders/myorders/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([order["_id"] for order in response.data], [own_order._id])

    def test_create_order_uses_frontend_shipping_payload(self):
        user = User.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="test-password",
        )
        product = Product.objects.create(
            name="Test product",
            price="25.00",
            countInStock=5,
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            "/api/orders/add/",
            {
                "orderItems": [
                    {
                        "product": product._id,
                        "qty": 2,
                        "price": "25.00",
                    }
                ],
                "shippingAddress": {
                    "address": "1 Main Street",
                    "city": "Test City",
                    "postalCode": "12345",
                    "country": "Test Country",
                },
                "paymentMethod": "Cash on Delivery",
                "itemsPrice": "50.00",
                "shippingPrice": "100.00",
                "taxPrice": "5.00",
                "totalPrice": "155.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["shippingPrice"], "100.00")
        self.assertEqual(response.data["paymentMethod"], "Cash on Delivery")
        self.assertEqual(len(response.data["orderItems"]), 1)
        self.assertEqual(response.data["shippingAddress"]["city"], "Test City")
        product.refresh_from_db()
        self.assertEqual(product.countInStock, 3)
        self.assertEqual(Order.objects.count(), 1)


class ProductAdminApiTests(APITestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Original product",
            price="25.00",
            brand="Original brand",
            countInStock=5,
            category="Original category",
            description="Original description",
        )
        self.update_url = f"/api/products/update/{self.product._id}/"

    def test_admin_can_update_product(self):
        admin = User.objects.create_user(
            username="admin",
            password="test-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=admin)

        response = self.client.put(
            self.update_url,
            {
                "name": "Updated product",
                "price": "30.00",
                "brand": "Updated brand",
                "countInStock": 7,
                "category": "Updated category",
                "description": "Updated description",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Updated product")
        self.assertEqual(self.product.countInStock, 7)

    def test_admin_can_create_product(self):
        admin = User.objects.create_user(
            username="admin",
            password="test-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=admin)

        response = self.client.post("/api/products/create/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(name="sample name").exists())

    def test_admin_can_upload_product_image_and_get_its_url(self):
        admin = User.objects.create_user(
            username="admin",
            password="test-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=admin)

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    "/api/products/upload/",
                    {
                        "product_id": str(self.product._id),
                        "image": SimpleUploadedFile(
                            "powerbank.png",
                            b"test image contents",
                            content_type="image/png",
                        ),
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["image"], "/images/powerbank.png")
        self.product.refresh_from_db()
        self.assertEqual(self.product.image.name, "powerbank.png")

    def test_non_admin_cannot_update_product(self):
        user = User.objects.create_user(
            username="customer",
            password="test-password",
        )
        self.client.force_authenticate(user=user)

        response = self.client.put(
            self.update_url,
            {"name": "Unauthorized update"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
