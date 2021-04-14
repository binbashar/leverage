from setuptools import setup

import leverage

setup(
    name='leverage',
    version=leverage.__version__,
    author='BinBash Inc',
    author_email='info@binbash.com.ar',
    description='Binbash Leverage Command-line Task Runner',
    long_description='A hack of Pynt for https://github.com/binbashar/leverage project',
    long_description_content_type="text/x-rst",
    url=leverage.__contact__, 
    packages=['leverage'],
    entry_points= {
        'console_scripts': ['leverage=leverage:main']}, 
    license='MIT License',
    python_requires=">=3.6",
    install_requires=[
        'yaenv == 1.2.2'
    ],
    keywords=['BINBASH', 'LEVERAGE'],
    classifiers=[
         'Development Status :: 3 - Alpha',
         'Intended Audience :: Developers',
         'Topic :: Software Development :: Build Tools',
         'License :: OSI Approved :: MIT License',
         'Programming Language :: Python :: 3',
         'Programming Language :: Python :: 3.6',
         'Programming Language :: Python :: 3.7',
         'Programming Language :: Python :: 3.8',
    ],
)
