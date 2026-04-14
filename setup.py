from setuptools import find_packages, setup


setup(
    name="nano-ant",
    version="0.3.0",
    description="A lightweight iterative harness agent framework.",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Nano Ant Contributors",
    author_email="opensource@nano-ant.dev",
    url="https://github.com/example/nano-ant",
    packages=find_packages(include=["nano_ant", "nano_ant.*"]),
    include_package_data=True,
    package_data={"nano_ant": ["prompts/*.txt"]},
    install_requires=["PyYAML>=6.0"],
    extras_require={
        "http": ["httpx>=0.27"],
        "dev": ["build>=1.2.2", "twine>=5.1.1"],
    },
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "nano-ant=nano_ant.cli:main",
            "ant=nano_ant.cli:main",
        ]
    },
)
