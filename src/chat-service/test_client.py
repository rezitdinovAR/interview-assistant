#!/usr/bin/env python3
"""
Простой тестовый клиент для chat-service
"""
import requests
import json
import sys


BASE_URL = "http://localhost:8084"
API_PREFIX = "/api/v1"


def chat(user_id: str, message: str):
    """Отправить сообщение в чат"""
    url = f"{BASE_URL}{API_PREFIX}/chat"
    payload = {
        "user_id": user_id,
        "message": message
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

    return response.json()


def reset_context(user_id: str):
    """Сбросить контекст пользователя"""
    url = f"{BASE_URL}{API_PREFIX}/reset"
    payload = {
        "user_id": user_id
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

    return response.json()


def health_check():
    """Проверить здоровье сервиса"""
    url = f"{BASE_URL}{API_PREFIX}/health"
    response = requests.get(url)
    response.raise_for_status()

    return response.json()


def main():
    print("=== Chat Service Test Client ===\n")

    # Проверка здоровья
    print("1. Health check...")
    try:
        health = health_check()
        print(f"   ✓ Service status: {health}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        sys.exit(1)

    # Тестовый пользователь
    user_id = "test_user_123"

    # Тест 1: Отправка сообщения
    print(f"\n2. Sending message as user '{user_id}'...")
    try:
        message = "Что такое замыкание в JavaScript?"
        print(f"   Question: {message}")

        response = chat(user_id, message)
        print(f"   Answer: {response['message'][:200]}...")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Тест 2: Второе сообщение (проверка контекста)
    print(f"\n3. Sending follow-up message...")
    try:
        message = "Можешь привести пример?"
        print(f"   Question: {message}")

        response = chat(user_id, message)
        print(f"   Answer: {response['message'][:200]}...")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Тест 3: Сброс контекста
    print(f"\n4. Resetting context for user '{user_id}'...")
    try:
        result = reset_context(user_id)
        print(f"   ✓ {result['message']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Тест 4: Сообщение после сброса
    print(f"\n5. Sending message after reset...")
    try:
        message = "Привет!"
        print(f"   Question: {message}")

        response = chat(user_id, message)
        print(f"   Answer: {response['message'][:200]}...")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    print("\n=== Tests completed ===")


if __name__ == "__main__":
    main()
