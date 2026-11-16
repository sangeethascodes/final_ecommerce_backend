from django.shortcuts import get_object_or_404, render
from django.db import transaction

from .models import Product,Order,OrderItem,ShippingAddress
from rest_framework.response import Response
from rest_framework.decorators import api_view,permission_classes
from rest_framework import serializers, status
from .serializer import ProductSerializer,UserSerializerWithToken,OrderSerializer,UserSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer # type: ignore
from rest_framework_simplejwt.views import TokenObtainPairView # type: ignore
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.permissions import IsAuthenticated,IsAdminUser

#for email purpose and verifying the email
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.views import View
from .utils import generate_token

# Create your views here.
@api_view(['GET'])
def getRoutes(request):
    myapis=[
        {
            "products":"http://127.0.0.1:8000/api/products",
            "product":"http://127.0.0.1:8000/api/product/1",
            "login": "http://127.0.0.1:8000/api/users/login",
            "signup": "http://127.0.0.1:8000/api/users/register"
        }
    ]
    return Response(myapis)

@api_view(['GET'])
def getProducts(request):
    products = Product.objects.all()
    serialize = ProductSerializer(products,many=True)
    return Response(serialize.data)

@api_view(['GET'])
def getProduct(request,pk):
    product = get_object_or_404(Product, _id=pk)
    serialize = ProductSerializer(product,many=False)
    return Response(serialize.data)

# class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
#     @classmethod
#     def get_token(cls,user):
        
#         token = super().get_token(user)
#         token['username'] = user.username
#         token['email'] = user.email
        
#         return token

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    email = serializers.CharField(write_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("username", None)

    def validate(self,attrs):
        identifier = attrs.pop("email").strip()
        user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            user = User.objects.filter(username__iexact=identifier).first()

        attrs["username"] = user.get_username() if user else identifier
        data = super().validate(attrs)
        serializer = UserSerializerWithToken(self.user).data
        for k,v in serializer.items():
            data[k]=v
        return data

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    

@api_view(['POST'])
def registerUser(request):
    data = request.data
    required_fields = ("fname", "lname", "email", "password")
    if any(not isinstance(data.get(field), str) or not data[field].strip() for field in required_fields):
        return Response(
            {"details": "First name, last name, email, and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = data["email"].strip()
    if User.objects.filter(username=email).exists():
        return Response(
            {"details": "An account with this email already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.create_user(
        first_name=data["fname"].strip(),
        last_name=data["lname"].strip(),
        username=email,
        email=email,
        password=data["password"],
        is_active=True,
    )

    return Response(
        {"details": "Your account has been created. You can now log in."},
        status=status.HTTP_201_CREATED,
    )


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def updateUserProfile(request):
    first_name = request.data.get('fname')
    last_name = request.data.get('lname')
    password = request.data.get('password', '')

    if not isinstance(first_name, str) or not first_name.strip():
        return Response(
            {'details': 'First name is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(last_name, str) or not last_name.strip():
        return Response(
            {'details': 'Last name is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(password, str):
        return Response(
            {'details': 'Password must be text.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if password and len(password) < 6:
        return Response(
            {'details': 'Password must be at least 6 characters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    user.first_name = first_name.strip()
    user.last_name = last_name.strip()
    if password:
        user.set_password(password)
    user.save()

    return Response(UserSerializer(user, many=False).data)


class ActivateAccountView(View):
    
    def get(self,request,uidb64,token):
        try:
            uid=force_str(urlsafe_base64_decode(uidb64))
            user=User.objects.get(pk=uid)
        except (TypeError, ValueError, User.DoesNotExist):
            user=None
            
        if user is not None and generate_token.check_token(user,token):
            user.is_active=True
            user.save()
            return render(request,'activatesuccess.html')
        else:
            return render(request,'activatefailure.html')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def addOrderItems(request):
    data = request.data
    order_items = data.get('orderItems')
    shipping_address = data.get('shippingAddress')

    if not isinstance(order_items, list) or not order_items:
        return Response(
            {'details': 'No Order Items'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(shipping_address, dict) or any(
        not shipping_address.get(field)
        for field in ('address', 'city', 'postalCode', 'country')
    ):
        return Response(
            {'details': 'A complete shipping address is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if any(data.get(field) is None for field in ('taxPrice', 'shippingPrice', 'totalPrice')):
        return Response(
            {'details': 'Order totals are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validated_items = []
    for item_data in order_items:
        product = get_object_or_404(Product, _id=item_data.get('product'))
        try:
            quantity = int(item_data.get('qty', 0))
        except (TypeError, ValueError):
            quantity = 0

        if quantity < 1 or quantity > product.countInStock:
            return Response(
                {'details': f'Invalid quantity for {product.name}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        validated_items.append((product, quantity, item_data.get('price', product.price)))

    with transaction.atomic():
        order = Order.objects.create(
            user=request.user,
            payementMethod=data.get('paymentMethod', 'Cash on Delivery'),
            taxPrice=data['taxPrice'],
            shippingPrice=data['shippingPrice'],
            totalPrice=data['totalPrice'],
        )

        ShippingAddress.objects.create(
            order=order,
            address=shipping_address['address'],
            city=shipping_address['city'],
            postalCode=shipping_address['postalCode'],
            country=shipping_address['country'],
        )

        for product, quantity, price in validated_items:
            OrderItem.objects.create(
                product=product,
                order=order,
                name=product.name,
                qty=quantity,
                price=price,
                image=product.image.url if product.image else '',
            )

            product.countInStock -= quantity
            product.save()

    serializer = OrderSerializer(order, many=False)
    return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def getMyOrders(request):
    user=request.user
    orders=user.order_set.all()
    serializer=OrderSerializer(orders,many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def getOrders(request):
    orders=Order.objects.all()
    serializer=OrderSerializer(orders,many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def getOrderById(request,pk):
    user=request.user
    
    try:
        order=Order.objects.get(_id=pk)
        if user.is_staff or order.user==user:
            serializer=OrderSerializer(order,many=False)
            return Response(serializer.data)
        else:
            Response({'details':'Not authorized to view this order'},status=status.HTTP_400_BAD_REQUEST)
            
    except:
        return Response({
            'details':'Order does not exist'
        },status=status.HTTP_400_BAD_REQUEST)
        
        
#admin views
@api_view(['POST'])
@permission_classes([IsAdminUser])
def createProduct(request):
    user=request.user
    
    product=Product.objects.create(
        user=user,
        name='sample name',
        price=0,
        brand='sample brand',
        countInStock=0,
        category='sample category',
        description='sample description'
        
    )
    
    serializer=ProductSerializer(product,many=False)
    return Response(serializer.data)

@api_view(['PUT'])
@permission_classes([IsAdminUser])
def updateProduct(request,pk):
    data=request.data
    product=Product.objects.get(_id=pk)
    product.name=data['name']
    product.price=data['price']
    product.brand=data['brand']
    product.countInStock=data['countInStock']
    product.category=data['category']
    product.description=data['description']
    product.save()
    serializer=ProductSerializer(product,many=False)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def uploadImage(request):
    data=request.data
    product_id=data['product_id']
    product=Product.objects.get(_id=product_id)
    image=request.FILES.get('image')
    if image is None:
        return Response({'detail': 'No image was uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

    product.image=image
    product.save()
    serializer=ProductSerializer(product,many=False)
    return Response(serializer.data)

@api_view(['DELETE'])
# @permission_classes([IsAdminUser])
def deleteProduct(request,pk):
    product=Product.objects.get(_id=pk)
    product.delete()
    return Response('Product Deleted...')


@api_view(['GET'])
@permission_classes([IsAdminUser])
def getUsers(request):
    users=User.objects.all()
    serializer=UserSerializer(users,many=True)
    return Response(serializer.data)