from .models import User
from rest_framework import serializers
from others.utils import calculate_streak


class SignUpSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'name', 'password', 'confirm_password']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Password fields do not match.")
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            name=validated_data.get('name', ''),
            password=validated_data['password']
        )
        return user





class SignInSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={'input_type': 'password'})
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = User.objects.filter(email=email).first()
            if user:
                if not user.check_password(password):
                     raise serializers.ValidationError("Invalid credentials")
                if not user.is_active:
                    raise serializers.ValidationError("User is not active")
                if user.block:
                    raise serializers.ValidationError("User is blocked")
                attrs['user'] = user
                return attrs
            else:
                raise serializers.ValidationError("User not found")
        raise serializers.ValidationError("Email and password are required")





class UserProfileSerializer(serializers.ModelSerializer):

    streak = serializers.SerializerMethodField()
    total_checkin = serializers.SerializerMethodField()
    old_password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        exclude = ['block', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions', 'date_joined']
        read_only_fields = ['id', 'email', 'role']
        extra_kwargs = {'password': {'write_only': True}}

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        old_password = validated_data.pop('old_password', None)

        # Update all other fields sent in the request
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Handle password change separately if provided
        if password:
            if not old_password:
                raise serializers.ValidationError({"old_password": "Old password is required to set a new one."})
            if not instance.check_password(old_password):
                raise serializers.ValidationError({"old_password": "Old password does not match."})
            instance.set_password(password)

        instance.save()
        return instance

    def get_streak(self, obj):
        return calculate_streak(obj)

    def get_total_checkin(self, obj):
        return obj.checkins.count()
