from typing import Callable, Iterable
from toolz.curried import reduce

class TreeType(dict):
    
    def __getitem__(self, key):
        # return self[key] if key in self else self.setdefault(key, TreeType())
        if key not in self:
            self[key] = TreeType()
        return super().__getitem__(key)
    
    
    @classmethod
    def tree_expand(cls, tree: dict) -> 'TreeType':
        expanded_tree = cls()
        for key, value in tree.items():
            path = eval(key)
            # par,_= scan(lambda carry, x: (carry[x], None), expanded_tree, path[:-1])
            
            carry = expanded_tree
            for node in path[:-1]:
                if not isinstance(carry[node], TreeType):
                    carry[node] = TreeType(__root__=carry[node])
                carry = carry[node]
                
            par = carry[path[-1]]
            if par is not None:
                par['__root__'] = value
            else:
                carry[path[-1]] = value
        return expanded_tree
    
    def get_term(self,term):
        return reduce(lambda acc,y:acc[y], term, self)

    def reduce(self, f, init):
        if not isinstance(self, TreeType):
            return self
        else:
            return sum(map(lambda x: TreeType.reduce(x, f, init), self.values()))
        # return reduce(f, self.values(), init)
        
    def sum(self) -> int:
        return self.reduce(lambda x,y: x+y, 0)
    
    def isempty(self) -> bool:
        return not any(self.values())
    
if __name__ == '__main__':
    t = TreeType.tree_expand({"['ab','bb']":1,
                              "['ab']":2,
                              "['ab','c']":3,
                              "['d']":4})
    print(t)
    print(t['ab'])
    print(t['d'])
    print(t.sum())
    print(t['ab'].sum())
    print(t.isempty())
    print(t['ab']['e'])
    print(t['ab']['e'].isempty())
