"""
Setup script for the fraud-common shared library.

This package provides reusable configuration, domain models, exceptions,
and logging utilities for all microservices in the Real-Time Fraud Detection
Platform.

Install in development mode::

    pip install -e .
"""

from setuptools import find_packages, setup

setup(
    name="fraud-common",
    version="0.1.0",
    description="Shared library for the Real-Time Fraud Detection Platform.",
    long_description="Provides configuration, domain models, exceptions, "
    "and structured logging utilities used across all "
    "fraud detection microservices.",
    author="Fraud Detection Platform Team",
    python_requires=">=3.11",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "aiokafka>=0.9.0",
        "redis>=5.0.0",
        "sqlalchemy>=2.0.0",
        "asyncpg>=0.29.0",
        "structlog>=23.2.0",
        "httpx>=0.25.0",
        "grpcio>=1.60.0",
        "grpcio-tools>=1.60.0",
        "uvicorn>=0.24.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.23.0",
            "pytest-cov>=4.1.0",
            "mypy>=1.7.0",
            "ruff>=0.1.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
    ],
)
