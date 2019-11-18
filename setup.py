import setuptools

with open('README.md', 'r') as fd:
    long_description = fd.read()

setuptools.setup(
    name='picbasket',
    version='0.1',
    author='Evan Wegley',
    author_email='tomocafe@pm.me',
    description='',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='http://github.com/tomocafe/picbasket',
    license='MIT',
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': [
            'picbasket-cli=picbasket.cli:main',
            'picbasket=picbasket.app:main'
        ],
    },
    #classifiers=[
    #
    #],
    install_requires=[
        'Pillow',
        'imagehash',
        'exifread'
    ],
    python_requires='>=3.6'
)
