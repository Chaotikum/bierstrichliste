def liftA2(f, a, b):
    return a.ap(b).map(f)

class Left:
    def __init__(self, value):
        self.value = value

    def bind(self, f):
        return self

    def map(self, f):
        return self

    def ap(self, m):
        return self

    def __repr__(self):
        return "Left(%s)" % self.value


class Right:
    def __init__(self, value):
        self.value = value

    def bind(self, f):
        return f(self.value)

    def map(self, f):
        return Right(self.bind(f))

    def ap(self, m):
        return Right(self.value(m.value))

    def __repr__(self):
        return "Right(%s)" % self.value


class Writer:
    def __init__(self, monoid, value):
        self.monoid = monoid
        self.value = value

    def run(self):
        return (self.value, self.monoid)

    def bind(self, f):
        a = f(self.value)
        return Writer(self.monoid + a.monoid, a.value)

    def map(self, f):
        return Writer(self.monoid, f(self.value))

    def ap(self, m):
        return Writer(self.monoid + m.monoid, self.value(m.value))

    def __repr__(self):
        return "Writer(%s, %s)" % (self.monoid, self.value)
