"""
    Query and regression tests,
    plus tests for django-mongodb-engine specific features
"""
import datetime
from django.db.models import F, Q
from django.db.utils import DatabaseError
from django.contrib.sites.models import Site

from pymongo.objectid import ObjectId, InvalidId
from pymongo import ASCENDING, DESCENDING
from django_mongodb_engine.serializer import LazyModelInstance

from .utils import TestCase, get_collection
from models import *

class QueryTests(TestCase):
    """ Backend-agnostic query tests """

    def assertQuerysetEqual(self, a, b):
        self.assertEqual(list(a), list(b))

    def test_add_and_delete_blog(self):
        Blog.objects.create(title='blog1')
        self.assertEqual(Blog.objects.count(), 1)
        blog2 = Blog.objects.create(title='blog2')
        self.assertIsInstance(blog2.pk, unicode)
        self.assertEqual(Blog.objects.count(), 2)
        blog2.delete()
        self.assertEqual(Blog.objects.count(), 1)
        Blog.objects.filter(title='blog1').delete()
        self.assertEqual(Blog.objects.count(), 0)

    def test_simple_filter(self):
        blog1 = Blog.objects.create(title="same title")
        Blog.objects.create(title="same title")
        Blog.objects.create(title="another title")
        self.assertEqual(Blog.objects.count(), 3)
        self.assertEqual(Blog.objects.get(pk=blog1.pk), blog1)
        self.assertEqual(Blog.objects.filter(title="same title").count(), 2)
        self.assertEqual(Blog.objects.filter(title="same title").filter(pk=blog1.pk).count(), 1)
        self.assertEqual(Blog.objects.filter(title__startswith="same").count(), 2)
        self.assertEqual(Blog.objects.filter(title__istartswith="SAME").count(), 2)
        self.assertEqual(Blog.objects.filter(title__endswith="title").count(), 3)
        self.assertEqual(Blog.objects.filter(title__iendswith="Title").count(), 3)
        self.assertEqual(Blog.objects.filter(title__icontains="same").count(), 2)
        self.assertEqual(Blog.objects.filter(title__contains="same").count(), 2)
        self.assertEqual(Blog.objects.filter(title__iexact="same Title").count(), 2)
        self.assertEqual(Blog.objects.filter(title__regex="s.me.*").count(), 2)
        self.assertEqual(Blog.objects.filter(title__iregex="S.me.*").count(), 2)

        for record in [{'name' : 'igor', 'surname' : 'duck', 'age' : 39},
                       {'name' : 'andrea', 'surname' : 'duck', 'age' : 29}]:
            Person.objects.create(**record)
        self.assertEqual(Person.objects.filter(name="igor", surname="duck").count(), 1)
        self.assertEqual(Person.objects.filter(age__gte=20, surname="duck").count(), 2)

    def test_change_model(self):
        blog1 = Blog.objects.create(title="blog 1")
        self.assertEqual(Blog.objects.count(), 1)
        blog1.title = "new title"
        blog1.save()
        self.assertEqual(Blog.objects.count(), 1)
        self.assertEqual(blog1.title, Blog.objects.all()[0].title)

    def test_dates_ordering(self):
        now = datetime.datetime.now()
        before = now - datetime.timedelta(days=1)

        entry1 = Entry.objects.create(title="entry 1", date_published=now)
        entry2 = Entry.objects.create(title="entry 2", date_published=before)

        self.assertQuerysetEqual(Entry.objects.order_by('-date_published'),
                                 [entry1, entry2])
        self.assertQuerysetEqual(Entry.objects.order_by('date_published'),
                                 [entry2, entry1])

    def test_skip_limit(self):
        now = datetime.datetime.now()
        before = now - datetime.timedelta(days=1)

        Entry(title="entry 1", date_published=now).save()
        Entry(title="entry 2", date_published=before).save()
        Entry(title="entry 3", date_published=before).save()

        self.assertEqual(len(Entry.objects.order_by('-date_published')[:2]), 2)
        # With step
        self.assertEqual(len(Entry.objects.order_by('date_published')[1:2:1]), 1)
        self.assertEqual(len(Entry.objects.order_by('date_published')[1:2]), 1)

    def test_values_query(self):
        blog = Blog.objects.create(title='fooblog')
        entry = Entry.objects.create(blog=blog, title='footitle', content='foocontent')
        entry2 = Entry.objects.create(blog=blog, title='footitle2', content='foocontent2')
        self.assertQuerysetEqual(
            Entry.objects.values(),
            [{'blog_id' : blog.id, 'title' : u'footitle', 'id' : entry.id,
              'content' : u'foocontent', 'date_published' : None},
             {'blog_id' : blog.id, 'title' : u'footitle2', 'id' : entry2.id,
              'content' : u'foocontent2', 'date_published' : None}
            ]
        )
        self.assertQuerysetEqual(
            Entry.objects.values('blog'),
            [{'blog' : blog.id}, {'blog' : blog.id}]
        )
        self.assertQuerysetEqual(
            Entry.objects.values_list('blog_id', 'date_published'),
            [(blog.id, None), (blog.id, None)]
        )
        self.assertQuerysetEqual(
            Entry.objects.values('title', 'content'),
            [{'title' : u'footitle', 'content' : u'foocontent'},
             {'title' : u'footitle2', 'content' : u'foocontent2'}]
        )

    def test_dates_less_and_more_than(self):
        now = datetime.datetime.now()
        before = now + datetime.timedelta(days=1)
        after = now - datetime.timedelta(days=1)

        entry1 = Entry.objects.create(title="entry 1", date_published=now)
        entry2 = Entry.objects.create(title="entry 2", date_published=before)
        entry3 = Entry.objects.create(title="entry 3", date_published=after)

        self.assertQuerysetEqual(Entry.objects.filter(date_published=now), [entry1])
        self.assertQuerysetEqual(Entry.objects.filter(date_published__lt=now), [entry3])
        self.assertQuerysetEqual(Entry.objects.filter(date_published__gt=now), [entry2])

    def test_mongodb_fields(self):
        t1 = TestFieldModel.objects.create(
            title="p1", mlist=["ab", {'a':23, "b":True  }], slist=["bc", "ab"],
            mdict = {'a':23, "b":True  }, mset=["a", 'b', "b"]
        )
        t = TestFieldModel.objects.get(id=t1.id)
        self.assertEqual(t.mlist, ["ab", {'a':23, "b":True  }])
        self.assertEqual(t.mlist_default, ["a", "b"])
        self.assertEqual(t.slist, ["ab", "bc"])
        self.assertEqual(t.slist_default, ["a", "b"])
        self.assertEqual(t.mdict, {'a':23, "b":True  })
        self.assertEqual(t.mdict_default, {"a": "a", 'b':1})
        self.assertEqual(sorted(t.mset), ["a", 'b'])
        self.assertEqual(sorted(t.mset_default), ["a", 'b'])

        from django_mongodb_engine.query import A
        t2 = TestFieldModel.objects.get(mlist=A("a", 23))
        self.assertEqual(t1.pk, t2.pk)

    def test_simple_foreign_keys(self):
        blog1 = Blog.objects.create(title="Blog")
        entry1 = Entry.objects.create(title="entry 1", blog=blog1)
        entry2 = Entry.objects.create(title="entry 2", blog=blog1)
        self.assertEqual(Entry.objects.count(), 2)
        for entry in Entry.objects.all():
            self.assertEqual(
                blog1,
                entry.blog
            )
        blog2 = Blog.objects.create(title="Blog")
        Entry.objects.create(title="entry 3", blog=blog2)
        self.assertQuerysetEqual(Entry.objects.filter(blog=blog1.pk),
                                 [entry1, entry2])
        # XXX Uncomment this if the corresponding Django has been fixed
        #entry_without_blog = Entry.objects.create(title='x')
        #self.assertEqual(Entry.objects.get(blog=None), entry_without_blog)
        #self.assertEqual(Entry.objects.get(blog__isnull=True), entry_without_blog)

    def test_foreign_keys_bug(self):
        blog1 = Blog.objects.create(title="Blog")
        entry1 = Entry.objects.create(title="entry 1", blog=blog1)
        self.assertQuerysetEqual(Entry.objects.filter(blog=blog1), [entry1])

    def test_update(self):
        blog1 = Blog.objects.create(title="Blog")
        blog2 = Blog.objects.create(title="Blog 2")
        entry1 = Entry.objects.create(title="entry 1", blog=blog1)

        Entry.objects.filter(pk=entry1.pk).update(blog=blog2)
        self.assertQuerysetEqual(Entry.objects.filter(blog=blog2), [entry1])

        Entry.objects.filter(blog=blog2).update(title="Title has been updated")
        self.assertQuerysetEqual(Entry.objects.filter()[0].title, "Title has been updated")

        Entry.objects.filter(blog=blog2).update(title="Last Update Test", blog=blog1)
        self.assertQuerysetEqual(Entry.objects.filter()[0].title, "Last Update Test")

        self.assertEqual(Entry.objects.filter(blog=blog1).count(), 1)
        self.assertEqual(Blog.objects.filter(title='Blog').count(), 1)
        Blog.objects.update(title='Blog')
        self.assertEqual(Blog.objects.filter(title='Blog').count(), 2)

    def test_update_id(self):
        self.assertRaisesRegexp(DatabaseError, "Can not modify _id",
                                Entry.objects.update, id=ObjectId())

    def test_update_with_F(self):
        john = Person.objects.create(name='john', surname='nhoj', age=42)
        andy = Person.objects.create(name='andy', surname='ydna', age=-5)
        Person.objects.update(age=F('age')+7)
        self.assertEqual(Person.objects.get(pk=john.id).age, 49)
        self.assertEqual(Person.objects.get(id=andy.pk).age, 2)

    def test_regex_matchers(self):
        objs = [Blog.objects.create(title=title) for title in
                ('Hello', 'worLd', '[(', '**', '\\')]
        self.assertEqual(list(Blog.objects.filter(title__startswith='h')), [])
        self.assertEqual(list(Blog.objects.filter(title__istartswith='h')), [objs[0]])
        self.assertEqual(list(Blog.objects.filter(title__contains='(')), [objs[2]])
        self.assertEqual(list(Blog.objects.filter(title__endswith='\\')), [objs[4]])

    def test_multiple_regex_matchers(self):
        objs = [Person.objects.create(name=a, surname=b) for a, b in
                (name.split() for name in ['donald duck', 'dagobert duck', 'daisy duck'])]

        filters = dict(surname__startswith='duck', surname__istartswith='duck',
                       surname__endswith='duck', surname__iendswith='duck',
                       surname__contains='duck', surname__icontains='duck')
        base_query = Person.objects \
                        .filter(**filters) \
                        .filter(~Q(surname__contains='just-some-random-condition',
                                   surname__endswith='hello world'))
        #base_query = base_query | base_query

        self.assertEqual(base_query.filter(name__iendswith='d')[0], objs[0])
        self.assertEqual(base_query.filter(name='daisy').get(), objs[2])

    def test_multiple_filter_on_same_name(self):
        Blog.objects.create(title='a')
        self.assertEqual(
            Blog.objects.filter(title='a').filter(title='a').filter(title='a').get(),
            Blog.objects.get()
        )
        self.assertQuerysetEqual(
            Blog.objects.filter(title='a').filter(title='b').filter(title='a'),
            []
        )

    def test_negated_Q(self):
        blogs = [Blog.objects.create(title=title) for title in
                 ('blog', 'other blog', 'another blog')]
        self.assertQuerysetEqual(
            Blog.objects.filter(title='blog') | Blog.objects.filter(~Q(title='another blog')),
            [blogs[0], blogs[1]]
        )
        self.assertRaises(
            DatabaseError,
            lambda: Blog.objects.filter(~Q(title='blog') & ~Q(title='other blog')).get()
        )
        self.assertQuerysetEqual(
            Blog.objects.filter(~Q(title='another blog')
                                | ~Q(title='blog')
                                | ~Q(title='aaaaa')
                                | ~Q(title='fooo')
                                | Q(title__in=[b.title for b in blogs])),
            blogs
        )
        self.assertEqual(
            Blog.objects.filter(Q(title__in=['blog', 'other blog']),
                                ~Q(title__in=['blog'])).get(),
            blogs[1]
        )
        self.assertEqual(
            Blog.objects.filter().exclude(~Q(title='blog')).get(),
            blogs[0]
        )

    def test_simple_or_queries(self):
        obj1 = Simple.objects.create(a=1)
        obj2 = Simple.objects.create(a=1)
        obj3 = Simple.objects.create(a=2)
        obj4 = Simple.objects.create(a=3)

        self.assertQuerysetEqual(
            Simple.objects.filter(a=1),
            [obj1, obj2]
        )
        self.assertQuerysetEqual(
            Simple.objects.filter(a=1) | Simple.objects.filter(a=2),
            [obj1, obj2, obj3]
        )
        self.assertQuerysetEqual(
            Simple.objects.filter(Q(a=2) | Q(a=3)),
            [obj3, obj4]
        )

        self.assertQuerysetEqual(
            Simple.objects.filter(Q(Q(a__lt=4) & Q(a__gt=2)) | Q(a=1)).order_by('id'),
            [obj1, obj2, obj4]
        )

    def test_date_datetime_and_time(self):
        self.assertEqual(DateModel().datelist, DateModel._datelist_default)
        self.assert_(DateModel().datelist is not DateModel._datelist_default)
        DateModel.objects.create()
        self.assertNotEqual(DateModel.objects.get().datetime, None)
        DateModel.objects.update(
            time=datetime.time(hour=3, minute=5, second=7),
            date=datetime.date(year=2042, month=3, day=5),
            datelist=[datetime.date(2001, 1, 2)]
        )
        self.assertEqual(
            DateModel.objects.values_list('time', 'date', 'datelist').get(),
            (datetime.time(hour=3, minute=5, second=7),
             datetime.date(year=2042, month=3, day=5),
             [datetime.date(year=2001, month=1, day=2)])
        )

class MongoDBEngineTests(TestCase):
    """ Tests for mongodb-engine specific features """
    def test_mongometa(self):
        self.assertEqual(Entry._meta.descending_indexes, ['title'])

    def test_lazy_model_instance(self):
        l1 = LazyModelInstance(Entry, 'some-pk')
        l2 = LazyModelInstance(Entry, 'some-pk')

        self.assertEqual(l1, l2)

        obj = Entry(title='foobar')
        obj.save()

        l3 = LazyModelInstance(Entry, obj.id)
        self.assertEqual(l3._wrapped, None)
        self.assertEqual(obj, l3)
        self.assertNotEqual(l3._wrapped, None)

    def test_lazy_model_instance_in_list(self):
        from django.conf import settings
        from django.db import connections
        from bson.errors import InvalidDocument

        obj = TestFieldModel()
        related = DynamicModel(gen=42)
        obj.mlist.append(related)
        self.assertRaises(InvalidDocument, obj.save)

        settings.MONGODB_AUTOMATIC_REFERENCING = True
        connections._connections.values()[0]._add_serializer()
        obj.save()
        self.assertNotEqual(related.id, None)
        obj = TestFieldModel.objects.get()
        self.assertEqual(obj.mlist[0]._wrapped, None)
        # query will be done NOW:
        self.assertEqual(obj.mlist[0].gen, 42)
        self.assertNotEqual(obj.mlist[0]._wrapped, None)

    def test_nice_yearmonthday_query_exception(self):
        for x in ('year', 'month', 'day'):
            key = 'date_published__%s' % x
            self.assertRaisesRegexp(DatabaseError, "MongoDB does not support year/month/day queries",
                                    lambda: Entry.objects.get(**{key : 1}))

    def test_nice_int_objectid_exception(self):
        msg = "AutoField \(default primary key\) values must be strings " \
              "representing an ObjectId on MongoDB \(got %r instead\)"
        self.assertRaisesRegexp(InvalidId, msg % u'helloworld...',
                                Simple.objects.create, id='helloworldwhatsup')
        self.assertRaisesRegexp(
            InvalidId, (msg % u'5') + ". Please make sure your SITE_ID contains a valid ObjectId.",
            Site.objects.get, id='5'
        )

    def test_generic_field(self):
        for obj in [['foo'], {'bar' : 'buzz'}]:
            id = DynamicModel.objects.create(gen=obj).id
            self.assertEqual(DynamicModel.objects.get(id=id).gen, obj)

class IndexTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        call_command('sqlindexes', 'general')

    def assertHaveIndex(self, field_name, direction=ASCENDING):
        info = get_collection(IndexTestModel).index_information()
        index_name = field_name + ['_1', '_-1'][direction==DESCENDING]
        self.assertIn(index_name, info)
        self.assertIn((field_name, direction), info[index_name]['key'])

    def test_regular_indexes(self):
        self.assertHaveIndex('regular_index')

    def test_custom_columns(self):
        self.assertHaveIndex('foo')
        self.assertHaveIndex('spam')

    def test_foreignkey(self):
        self.assertHaveIndex('foreignkey_index_id')

    def test_descending(self):
        self.assertHaveIndex('descending_index', DESCENDING)
        self.assertHaveIndex('bar', DESCENDING)
