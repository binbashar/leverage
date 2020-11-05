from setuptools import setup
import leverage

setup(
    name = "leverage",
    version = leverage.__version__,
    author = "BinBash Inc",
    author_email = "info@binbash.com.ar",
    description = "Lightweight Python Build Tool.",
    long_description = "A hack of Pynt for https://github.com/binbashar/leverage project",
    long_description_content_type = "text/x-rst",
    url = leverage.__contact__, 
    packages = ["leverage"],
    entry_points =  {'console_scripts': ['leverage=leverage:main']}, 
    license = "MIT License",
    install_requires = [
       "GitPython >= 3.1.11",
   ],
)
