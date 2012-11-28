#!/usr/bin/python

"""
Unit tests for the _microbuild.microbuild module.

Run these tests using `python -m _microbuild.tests.microbuild` from project root directory.
"""

import unittest

from .. import _microbuild

class TestBuildSimple(unittest.TestCase):
        
    def test_get_tasks(self):
        import build_scripts.simple
        ts = _microbuild._get_tasks(build_scripts.simple)
        print ts
        self.assertEqual(len(ts),5)
        
class TestBuildWithDependancies(unittest.TestCase):
        
    def test_get_tasks(self):
        import build_scripts.dependancies
        ts = _microbuild._get_tasks(build_scripts.dependancies)
        print ts
        self.assertEqual(len(ts),5)
        
class TestDecorationValidation(unittest.TestCase):

    def test_task_without_braces(self):
        with self.assertRaisesRegexp(Exception,
                                     'Replace use of @task with @task().'):
            import build_scripts.annotation_misuse_1

    def test_dependency_not_a_task(self):
        with self.assertRaisesRegexp(Exception,
                                     'function html.* is not a task.'):
            import build_scripts.annotation_misuse_2

    def test_dependency_not_a_function(self):
        with self.assertRaisesRegexp(Exception, '1234 is not a task.'):
            import build_scripts.annotation_misuse_3


        
class TestIgnore(unittest.TestCase):

    def test_ignore_before(self):
        import build_scripts.ignore_before
        _microbuild.build(build_scripts.ignore_before,["android"])

    def test_ignore_after(self):
        import build_scripts.ignore_after
        _microbuild.build(build_scripts.ignore_after,["android"])
        
class TestRuntimeError(unittest.TestCase):

    def test_stop_on_exception(self):
        import build_scripts.runtime_error as re
        with self.assertRaises(IOError):
            _microbuild.build(re,["android"])
        self.assertTrue(re.ran_images)
        self.assertFalse(hasattr(re, 'ran_android'))
        
    def test_exception_on_invalid_task_name(self):
        import build_scripts.build_with_params
        with self.assertRaisesRegexp(Exception,
                                     'task should be one of append_to_file, clean' +
                                     ', copy_file, echo, html, start_server, tests'):
            _microbuild.build(build_scripts.build_with_params,["doesnt_exist"])


class TestPartialTaskNames(unittest.TestCase):
    def setUp(self):
        import build_scripts.build_with_params
        self._mod = build_scripts.build_with_params
        self._mod.tasks_run = []
        
    def test_with_partial_name(self):
        _microbuild.build(self._mod, ["cl"])
        self.assertEqual(['clean[/tmp]'], self._mod.tasks_run)
        
    def test_with_partial_name_and_dependencies(self):
        _microbuild.build(self._mod, ["htm"])
        self.assertEqual(['clean[/tmp]','html'], self._mod.tasks_run)

    def test_exception_on_conflicting_partial_names(self):
        with self.assertRaisesRegexp(Exception,
                                     'Conflicting matches clean, copy_file for task c'):
            _microbuild.build(self._mod, ["c"])



class TestMultipleTasks(unittest.TestCase):
    def setUp(self):
        import build_scripts.build_with_params
        self._mod = build_scripts.build_with_params
        self._mod.tasks_run = []

    def test_dependency_is_run_only_once_unless_explicitly_invoked_again(self):
        _microbuild.build(self._mod, ["clean", "html", 'tests', "clean"])
        self.assertEqual(['clean[/tmp]', "html", "tests[]", "clean[/tmp]"],
                         self._mod.tasks_run)
        
    def test_multiple_partial_names(self):
        _microbuild.build(self._mod, ["cl", "htm"])
        self.assertEqual(['clean[/tmp]', "html"], self._mod.tasks_run)



class TesttaskArguments(unittest.TestCase):
    def setUp(self):
        import build_scripts.build_with_params
        self._mod = build_scripts.build_with_params
        self._mod.tasks_run = []

    def test_passing_optional_params_with_dependencies(self):
        _microbuild.build(self._mod, ["clean[~/project/foo]",
                                     'append_to_file[/foo/bar,ABCDEF]',
                                     "copy_file[/foo/bar,/foo/blah,False]",
                                     'start_server[8080]'])
        self.assertEqual(["clean[~/project/foo]",  'append_to_file[/foo/bar,ABCDEF]',
                          "copy_file[/foo/bar,/foo/blah,False]", 'start_server[8080,True]'],
                         self._mod.tasks_run)
        
    def test_invoking_varargs_task(self):
        _microbuild.build(self._mod, ['tests[test1,test2,test3]'])
        self.assertEqual(['tests[test1,test2,test3]'], 
                          self._mod.tasks_run)

    def test_partial_name_with_args(self):
        _microbuild.build(self._mod, ['co[foo,bar]','star'])
        self.assertEqual(['clean[/tmp]','copy_file[foo,bar,True]', 'start_server[80,True]'],
                         self._mod.tasks_run)


    def test_passing_keyword_args(self):
        _microbuild.build(self._mod, ['co[to=bar,from_=foo]','star[80,debug=False]', 'echo[foo=bar,blah=123]'])
        self.assertEqual(['clean[/tmp]','copy_file[foo,bar,True]', 'start_server[80,False]', 
                      'echo[blah=123,foo=bar]'], self._mod.tasks_run)


    def test_passing_varargs_and_keyword_args(self):
        _microbuild.build(self._mod, ['echo[1,2,3,some_str,foo=xyz,bar=123.3,111=333]'])
        self.assertEqual(['echo[1,2,3,some_str,111=333,foo=xyz,bar=123.3]'], self._mod.tasks_run)

    def test_validate_keyword_arguments_always_after_args(self):
        with self.assertRaisesRegexp(Exception,
                                     "Non keyword arg foo cannot follows" +
                                     " a keyword arg bar=123.3"):
            _microbuild.build(self._mod, ['echo[bar=123.3,foo]'])
        with self.assertRaisesRegexp(Exception,
                                     "Non keyword arg /foo1 cannot follows" +
                                     " a keyword arg from_=/foo"):
            _microbuild.build(self._mod, ['copy[from_=/foo,/foo1]'])


            
    def test_invalid_number_of_args(self):
        with self.assertRaisesRegexp(TypeError, 'takes exactly 2 arguments'):
             _microbuild.build(self._mod, ['append[1,2,3]'])

             
    def test_invalid_names_for_kwargs(self):
        with self.assertRaisesRegexp(TypeError,
                                     "got an unexpected keyword argument '1'"): 
            _microbuild.build(self._mod, ['copy[1=2,to=bar]'])
        with self.assertRaisesRegexp(TypeError,
                                     "got an unexpected keyword argument 'bar123'"): 
            _microbuild.build(self._mod, ['copy[bar123=2]'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
