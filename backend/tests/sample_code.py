"""Intentionally buggy sample snippets used across the test suite."""

CPP_ARRAY_OOB = """
#include <iostream>
int main() {
    int arr[5] = {1,2,3,4,5};
    int idx = 10;
    std::cout << arr[idx] << std::endl;
    return 0;
}
"""

CPP_NULL_DEREF = """
#include <iostream>
int main() {
    int *ptr = nullptr;
    std::cout << *ptr << std::endl;
    return 0;
}
"""

CPP_CLEAN = """
#include <iostream>
int add(int a, int b) {
    return a + b;
}
int main() {
    std::cout << add(2, 3) << std::endl;
    return 0;
}
"""

PYTHON_MUTABLE_DEFAULT = """
def process(items, cache={}):
    cache[len(items)] = items
    return cache
"""

PYTHON_BARE_EXCEPT_AND_EVAL = """
def run(user_input):
    try:
        eval(user_input)
    except:
        pass
"""

PYTHON_UNDEFINED_NAME = """
def compute():
    return undefined_variable + 1
"""

PYTHON_CLEAN = """
def add(a, b):
    return a + b
"""

PYTHON_NESTED_LOOPS = """
def pairs(items):
    result = []
    for i in items:
        for j in items:
            result.append((i, j))
    return result
"""

PYTHON_SYNTAX_ERROR = """
def broken(:
    pass
"""

JS_EVAL_AND_LOOSE_EQUALITY = """
function run(userInput) {
    if (userInput == "1") {
        eval(userInput);
    }
    return true;
}
"""

JS_UNUSED_VAR_AND_ASYNC_PROMISE_EXECUTOR = """
function build() {
    var unused = 42;
    return new Promise(async (resolve, reject) => {
        resolve(1);
    });
}
"""

JS_CLEAN = """
function add(a, b) {
    return a + b;
}
"""

JS_SYNTAX_ERROR = """
function broken( {
    return 1;
}
"""

JAVA_EMPTY_CATCH_AND_RESOURCE_LEAK = """
import java.io.FileReader;

public class Submission {
    public void readFile() {
        try {
            FileReader fr = new FileReader("data.txt");
            int c = fr.read();
            System.out.println(c);
        } catch (Exception e) {
        }
    }
}
"""

JAVA_HARDCODED_CREDENTIAL = """
public class Submission {
    public void connect() {
        String password = "hunter22";
        System.out.println(password);
    }
}
"""

JAVA_CLEAN = """
public class Submission {
    public int add(int a, int b) {
        return a + b;
    }
}
"""

JAVA_COMPILE_ERROR = """
public class Submission {
    public void broken() {
        int x = ;
    }
}
"""

