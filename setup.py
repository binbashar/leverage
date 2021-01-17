from setuptools import setup
import leverage

setup(
    name = 'leverage',
    version = leverage.__version__,
    author = 'BinBash Inc',
    author_email = 'info@binbash.com.ar',
    description = 'Lightweight Python Build Tool.',
    long_description = 'A hack of Pynt for https://github.com/binbashar/leverage project',
    long_description_content_type = "text/x-rst",
    url = leverage.__contact__, 
    packages = ['leverage'],
    entry_points =  {
        'console_scripts': ['leverage=leverage:main']}, 
    license = 'MIT License',
    install_requires = [
        'GitPython == 3.1.11',
        'yaenv == 1.4.1'
   ],
   keywords = ['BINBASH', 'LEVERAGE'],
   classifiers = [
        'Development Status :: 3 - Alpha',      # Either "3 - Alpha", "4 - Beta" or "5 - Production/Stable"
        'Intended Audience :: Developers',      # Define that your audience are developers
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',   # Pick a license
        'Programming Language :: Python :: 3',      # Supported pyhton versions
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
  ],
)
