from setuptools import setup, find_packages

setup(
    name='g_log',
    version='2.1',
    packages=find_packages(),
    description='Advanced logging solution',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Jonatan Gani',
    author_email='Jonatangani@protonmail.com',
    url='https://github.com/Jonatan-Gani/glog',
    # Add other parameters as needed
    install_requires=[
        'psutil'
    ]
)
