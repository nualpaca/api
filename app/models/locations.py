from . import db

class Location(db.Model):
    __tablename__ = 'locations'

    name = db.Column(db.String, primary_key=True)
    type = db.Column(db.String, primary_key=True)
    uid = db.Column(db.BigInteger, primary_key=True)
    address = db.Column(db.String, nullable=False)
    zipcode = db.Column(db.Integer)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    def to_json(self):
        d = {}
        for column in self.__table__.columns:
            d[column.name] = unicode(getattr(self, column.name))
        return d