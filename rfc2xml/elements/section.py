from .element import Element
from typing import Callable, Dict, List


class Section(Element):
    tag_name: str = "section"
    title: str = None
    number: str = None

    def traverse_sections(self, func: Callable[[Element, Dict], 'Section'], args=None):
        children = []
        for child in self.children:
            if isinstance(child, Section):
                child = func(child, args)
                child.children = child.traverse_sections(func)
            children.append(child)
        return children

    def __init__(self, title: str = None, number: str = None):
        super().__init__()
        self.title = title
        self.number = number

    def get_sections(self) -> List['Section']:
        o = []
        for child in self.children:
            if isinstance(child, Section):
                o.append(child)
        return o

    def get_attributes(self):
        attributes = {}
        if self.title is not None:
            attributes["title"] = self.title
        if self.number is not None:
            attributes["number"] = self.number
        return attributes

    def __str__(self):
        return str(self.number) + ". " + str(self.title)

    def __repr__(self):
        return self.__str__()
