#!/usr/bin/python

import pytest
import re
from .. import _pynt
import sys
from cStringIO import StringIO

class TestBuildSimple:
        
    def test_get_tasks(self):
        import build_scripts.simple
        ts = _pynt._get_tasks(build_scripts.simple)
        print ts
        assert len(ts) == 5
        
class TestBuildWithDependancies:
        
    def test_get_tasks(self):
        import build_scripts.dependancies
        ts = _pynt._get_tasks(build_scripts.dependancies)
        print ts
        assert len(ts) == 5
        
class TestDecorationValidation:

    def test_task_without_braces(self):
        with pytest.raises(Exception) as exc:
            import build_scripts.annotation_misuse_1
        assert 'Replace use of @task with @task().' in exc.value.message

    def test_dependency_not_a_task(self):
        with pytest.raises(Exception) as exc:
            import build_scripts.annotation_misuse_2
        assert re.findall('function html.* is not a task.', exc.value.message)

    def test_dependency_not_a_function(self):
        with pytest.raises(Exception) as exc:
            import build_scripts.annotation_misuse_3
        assert '1234 is not a task.' in exc.value.message


import contextlib
@contextlib.contextmanager
def mock_stdout():
    oldout, olderr =  sys.stdout,  sys.stderr
    try:
        out = [StringIO(),  StringIO()]
        sys.stdout, sys.stderr =  out
        yield out
    finally:
        sys.stdout, sys.stderr =  oldout,  olderr
        out[0] =  out[0].getvalue()
        out[1] =  out[1].getvalue()
                                                                                
        
class TestOptions:

    @pytest.fixture
    def module(self):
        import build_scripts.options as module
        module.tasks_run = []
        self.docs = {'clean': '', 'html': 'Generate HTML.',
                     'images': '''Prepare images.\n\nShould be ignored.''',
                     'android': 'Package Android app.'}
        return module
        
    def test_ignore_tasks(self, module):
        _pynt.build(module,["android"])
        assert ['clean', 'html', 'android'] == module.tasks_run

    def test_docs(self, module):
        tasks = _pynt._get_tasks(module)
        assert 4 == len(tasks)
        
        for task_ in tasks:
            assert task_.name in self.docs
            assert self.docs[task_.name] == task_.doc

    @pytest.mark.parametrize('args', [['-l'], ['--list-tasks'], []])
    def test_list_docs(self, module, args):
        with mock_stdout() as out: 
            _pynt.build(module,args)
        stdout = out[0]
        tasks = _pynt._get_tasks(module)
        for task in tasks:
            if task.ignored:
                assert re.findall('%s\s+%s\s+%s' % (task.name,"\[Ignored\]", task.doc), stdout)
            else:
                assert re.findall('%s\s+%s' % (task.name, task.doc), stdout)
            

            
class TestRuntimeError:

    def test_stop_on_exception(self):
        import build_scripts.runtime_error as re
        with pytest.raises(IOError):
            _pynt.build(re,["android"])
        assert re.ran_images
        assert not hasattr(re, 'ran_android')
        
    def test_exception_on_invalid_task_name(self):
        import build_scripts.build_with_params
        with pytest.raises(Exception) as exc:
            _pynt.build(build_scripts.build_with_params,["doesnt_exist"])
            
            assert 'task should be one of append_to_file, clean' \
                ', copy_file, echo, html, start_server, tests' in exc.value.message


class TestPartialTaskNames:
    def setup_method(self,method):
        import build_scripts.build_with_params
        self._mod = build_scripts.build_with_params
        self._mod.tasks_run = []
        
    def test_with_partial_name(self):
        _pynt.build(self._mod, ["cl"])
        assert ['clean[/tmp]'] ==  self._mod.tasks_run
        
    def test_with_partial_name_and_dependencies(self):
        _pynt.build(self._mod, ["htm"])
        assert ['clean[/tmp]','html'] ==  self._mod.tasks_run

    def test_exception_on_conflicting_partial_names(self):
        with pytest.raises(Exception) as exc:
            _pynt.build(self._mod, ["c"])
        assert 'Conflicting matches clean, copy_file for task c' in exc.value.message



class TestMultipleTasks:
    def setup_method(self,method):
        import build_scripts.build_with_params
        self._mod = build_scripts.build_with_params
        self._mod.tasks_run = []

    def test_dependency_is_run_only_once_unless_explicitly_invoked_again(self):
        _pynt.build(self._mod, ["clean", "html", 'tests', "clean"])
        assert ['clean[/tmp]', "html", "tests[]", "clean[/tmp]"] == self._mod.tasks_run
        
    def test_multiple_partial_names(self):
        _pynt.build(self._mod, ["cl", "htm"])
        assert ['clean[/tmp]', "html"] ==  self._mod.tasks_run



class TesttaskArguments:
    def setup_method(self,method):
        import build_scripts.build_with_params
        self._mod = build_scripts.build_with_params
        self._mod.tasks_run = []

    def test_passing_optional_params_with_dependencies(self):
        _pynt.build(self._mod, ["clean[~/project/foo]",
                                     'append_to_file[/foo/bar,ABCDEF]',
                                     "copy_file[/foo/bar,/foo/blah,False]",
                                     'start_server[8080]'])
        assert ["clean[~/project/foo]",  'append_to_file[/foo/bar,ABCDEF]', 
                "copy_file[/foo/bar,/foo/blah,False]", 'start_server[8080,True]'
            ] == self._mod.tasks_run
        
    def test_invoking_varargs_task(self):
        _pynt.build(self._mod, ['tests[test1,test2,test3]'])
        assert ['tests[test1,test2,test3]'] == self._mod.tasks_run

    def test_partial_name_with_args(self):
        _pynt.build(self._mod, ['co[foo,bar]','star'])
        assert ['clean[/tmp]','copy_file[foo,bar,True]', 'start_server[80,True]'
            ] == self._mod.tasks_run


    def test_passing_keyword_args(self):
        _pynt.build(self._mod, ['co[to=bar,from_=foo]','star[80,debug=False]', 'echo[foo=bar,blah=123]'])
        assert ['clean[/tmp]','copy_file[foo,bar,True]', 'start_server[80,False]', 
                      'echo[blah=123,foo=bar]'] == self._mod.tasks_run


    def test_passing_varargs_and_keyword_args(self):
        _pynt.build(self._mod, ['echo[1,2,3,some_str,foo=xyz,bar=123.3,111=333]'])
        assert ['echo[1,2,3,some_str,111=333,foo=xyz,bar=123.3]'] ==  self._mod.tasks_run

    def test_validate_keyword_arguments_always_after_args(self):
        with pytest.raises(Exception) as exc:
            _pynt.build(self._mod, ['echo[bar=123.3,foo]'])
        assert "Non keyword arg foo cannot follows" \
            " a keyword arg bar=123.3" in exc.value.message
        
        with pytest.raises(Exception) as exc:
            _pynt.build(self._mod, ['copy[from_=/foo,/foo1]'])

        assert "Non keyword arg /foo1 cannot follows" \
            " a keyword arg from_=/foo" in exc.value.message


            
    def test_invalid_number_of_args(self):
        with pytest.raises(TypeError) as exc: 
             _pynt.build(self._mod, ['append[1,2,3]'])
        assert 'takes exactly 2 arguments' in exc.value.message

             
    def test_invalid_names_for_kwargs(self):
        with pytest.raises(TypeError) as exc: 
            _pynt.build(self._mod, ['copy[1=2,to=bar]'])
        assert "got an unexpected keyword argument '1'" in exc.value.message
        
        with pytest.raises(TypeError) as exc: 
            _pynt.build(self._mod, ['copy[bar123=2]'])
        assert "got an unexpected keyword argument 'bar123'" in exc.value.message

