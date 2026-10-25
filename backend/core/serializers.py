"""Shared response shapes. ErrorSerializer documents the body every failure uses."""

from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField()


class ErrorSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "degraded"])
    version = serializers.CharField()
    database = serializers.ChoiceField(choices=["ok", "unavailable"])
    pgvector = serializers.BooleanField()
