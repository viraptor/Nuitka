#     Copyright 2016, Kay Hayen, mailto:kay.hayen@gmail.com
#
#     Part of "Nuitka", an optimizing Python compiler that is compatible and
#     integrates with CPython, but also works on its own.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
""" Standard plug-in to make multiprocessing work well on Windows.

On Windows, the multiprocessing modules forks new processes which then have
to start from scratch. This won't work if there is no "sys.executable" to
point to a "Python.exe" and won't use compiled code by default.

The issue applies to accelerated and standalone mode alike.
"""

from nuitka import Options
from nuitka.plugins.PluginBase import NuitkaPluginBase
from nuitka.utils import Utils


class NuitkaPluginMultiprocessingWorkaorunds(NuitkaPluginBase):
    """ This is to make multiprocess work with Nuitka and use compiled code.

        When running in accelerated mode, it's not good to fork a new Python
        instance to run other code, as that won't be accelerated. And when
        run in standalone mode, there may not even be a Python, but it's the
        same principle.

        So by default, this module is on and works around the behavior of the
        "multiprocess.forking" expectations.
    """
    plugin_name = "multiprocessing"

    def __init__(self):
        self.multiprocessing_added = False

    @staticmethod
    def createPreModuleLoadCode(module):
        full_name = module.getFullName()

        if full_name == "multiprocessing.forking":
            code = """\
import sys
sys.frozen = 1
sys.executable = sys.argv[0]
"""
            return code, """\
Monkey patching "multiprocessing" load environment."""


        return None, None

    @staticmethod
    def createPostModuleLoadCode(module):
        full_name = module.getFullName()

        if full_name == "multiprocessing.forking":
            code = """\
from multiprocessing.forking import ForkingPickler

class C:
   def f():
       pass

def _reduce_compiled_method(m):
    if m.im_self is None:
        return getattr, (m.im_class, m.im_func.__name__)
    else:
        return getattr, (m.im_self, m.im_func.__name__)

print type(_reduce_compiled_method)
ForkingPickler.register(type(C.f), _reduce_compiled_method)
"""
            return code, """\
Monkey patching "multiprocessing" for compiled methods."""


        return None, None

    def onModuleEncounter(self, module_filename, module_name, module_package,
                          module_kind):
        if module_name == "multiprocessing" and \
           module_package is None \
           and not self.multiprocessing_added:
            self.multiprocessing_added = True

            from nuitka.ModuleRegistry import getRootModules, addRootModule
            from nuitka.tree.Building import CompiledPythonModule, readSourceCodeFromFilename, createModuleTree

            for root_module in getRootModules():
                if root_module.isMainModule():
                    # First, build the module node and then read again from the
                    # source code.

                    slave_main_module = CompiledPythonModule(
                        name         = "__parents_main__",
                        package_name = None,
                        source_ref   = root_module.getSourceReference()
                    )

                    source_code = readSourceCodeFromFilename(
                        "__parents_main__",
                        root_module.getFilename()
                    )

                    # For the call stack, this may look bad or different to what
                    # CPython does. Using the "__import__" built-in to not spoil
                    # or use the module namespace.
                    source_code += """
__import__("sys").modules["__main__"] = __import__("sys").modules[__name__]
__import__("multiprocessing.forking").forking.main()"""

                    createModuleTree(
                        module      = slave_main_module,
                        source_ref  = root_module.getSourceReference(),
                        source_code = source_code,
                        is_main     = False
                    )

                    # This is an alternative entry point of course.
                    addRootModule(slave_main_module)

                    break
            else:
                assert False


class NuitkaPluginDetectorMultiprocessingWorkaorunds(NuitkaPluginBase):
    plugin_name = "multiprocessing"

    @staticmethod
    def isRelevant():
        return Utils.getOS() == "Windows" and not Options.shallMakeModule()

    def onModuleSourceCode(self, module_name, source_code):
        if module_name == "__main__":
            if "multiprocessing" in source_code and "freeze_support" in source_code:
                self.warnUnusedPlugin("Multiprocessing workarounds for compiled code on Windows.")

        return source_code
