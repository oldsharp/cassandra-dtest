from cql import ProgrammingError
from dtest import Tester, debug
from tools import since
import os
import datetime
import random
import uuid

class TestUserTypes(Tester):

    def __init__(self, *args, **kwargs):
        Tester.__init__(self, *args, **kwargs)

    @since('2.1')
    def test_type_renaming(self):
      """
      Confirm that types can be renamed and the proper associations are updated.
      """
      cluster = self.cluster
      cluster.populate(3).start()
      node1, node2, node3 = cluster.nodelist()
      cursor = self.cql_connection(node1).cursor()
      self.create_ks(cursor, 'user_type_renaming', 2)

      stmt = """
            CREATE TYPE simple_type (
            user_number int
            )
         """
      cursor.execute(stmt)

      stmt = """
            CREATE TABLE simple_table (
            id uuid PRIMARY KEY,
            number simple_type
            )
         """
      cursor.execute(stmt)

      stmt = """
          ALTER TYPE simple_type rename to renamed_type;
         """
      cursor.execute(stmt)

      stmt = """
          SELECT type_name from system.schema_usertypes;
         """
      cursor.execute(stmt)
      # we should only have one user type in this test
      self.assertEqual(1, cursor.rowcount)

      # finally let's look for the new type name
      self.assertEqual(cursor.fetchone()[0], u'renamed_type')

    @since('2.1')
    def test_nested_type_renaming(self):
      """
      Confirm type renaming works as expected on nested types.
      """
      cluster = self.cluster
      cluster.populate(3).start()
      node1, node2, node3 = cluster.nodelist()
      cursor = self.cql_connection(node1).cursor()
      self.create_ks(cursor, 'nested_user_type_renaming', 2)

      stmt = """
            CREATE TYPE simple_type (
            user_number int,
            user_text text
            )
         """
      cursor.execute(stmt)

      stmt = """
            CREATE TYPE another_type (
            somefield simple_type
            )
         """
      cursor.execute(stmt)

      stmt = """
            CREATE TYPE yet_another_type (
            some_other_field another_type
            )
         """
      cursor.execute(stmt)

      stmt = """
            CREATE TABLE uses_nested_type (
            id uuid PRIMARY KEY,
            field_name yet_another_type
            )
         """
      cursor.execute(stmt)

      # let's insert some basic data using the nested types
      _id = uuid.uuid4()
      stmt = """
            INSERT INTO uses_nested_type (id, field_name)
            VALUES (%s, {some_other_field: {somefield: {user_number: 1, user_text: 'original'}}});
         """ % _id
      cursor.execute(stmt)

      # rename one of the types used in the nesting
      stmt = """
            ALTER TYPE another_type rename to another_type2;
         """
      cursor.execute(stmt)

      # confirm nested data can be queried without error
      stmt = """
            SELECT field_name FROM uses_nested_type where id = {id}
         """.format(id=_id)
      cursor.execute(stmt)

      data = cursor.fetchone()[0]
      self.assertIn('original', data)

      # confirm we can alter/query the data after altering the type
      stmt = """
            UPDATE uses_nested_type
            SET field_name = {some_other_field: {somefield: {user_number: 2, user_text: 'altered'}}}
            WHERE id=%s;
         """ % _id
      cursor.execute(stmt)

      stmt = """
            SELECT field_name FROM uses_nested_type where id = {id}
         """.format(id=_id)
      cursor.execute(stmt)

      data = cursor.fetchone()[0]
      self.assertIn('altered', data)

      # and confirm we can add/query new data after the type rename
      _id = uuid.uuid4()
      stmt = """
            INSERT INTO uses_nested_type (id, field_name)
            VALUES (%s, {some_other_field: {somefield: {user_number: 1, user_text: 'inserted'}}});
         """ % _id
      cursor.execute(stmt)

      stmt = """
            SELECT field_name FROM uses_nested_type where id = {id}
         """.format(id=_id)
      cursor.execute(stmt)

      data = cursor.fetchone()[0]
      self.assertIn('inserted', data)


    @since('2.1')
    def test_nested_type_dropping(self):
      """
      Confirm a user type can't be dropped when being used by another user type. 
      """
      cluster = self.cluster
      cluster.populate(3).start()
      node1, node2, node3 = cluster.nodelist()
      cursor = self.cql_connection(node1).cursor()
      self.create_ks(cursor, 'nested_user_type_dropping', 2)

      stmt = """
            CREATE TYPE simple_type (
            user_number int,
            user_text text
            )
         """
      cursor.execute(stmt)

      stmt = """
            CREATE TYPE another_type (
            somefield simple_type
            )
         """
      cursor.execute(stmt)

      stmt = """
            DROP TYPE simple_type;
         """
      with self.assertRaisesRegexp(ProgrammingError, 'Cannot drop user type simple_type as it is still used by user type another_type'):
        cursor.execute(stmt)

      # drop the type that's impeding the drop, and then try again
      stmt = """
            DROP TYPE another_type;
         """
      cursor.execute(stmt)

      stmt = """
            DROP TYPE simple_type;
         """
      cursor.execute(stmt)

      # now let's have a look at the system schema and make sure no user types are defined
      stmt = """
            SELECT type_name from system.schema_usertypes;
         """
      cursor.execute(stmt)
      self.assertEqual(0, cursor.rowcount)

    @since('2.1')
    def test_type_enforcement(self):
      """
      Confirm error when incorrect data type used for user type
      """
      cluster = self.cluster
      cluster.populate(3).start()
      node1, node2, node3 = cluster.nodelist()
      cursor = self.cql_connection(node1).cursor()
      self.create_ks(cursor, 'user_type_enforcement', 2)

      stmt = """
            CREATE TYPE simple_type (
            user_number int
            )
         """
      cursor.execute(stmt)

      stmt = """
            CREATE TABLE simple_table (
            id uuid PRIMARY KEY,
            number simple_type
            )
         """
      cursor.execute(stmt)

      # here we will attempt an insert statement which should fail
      # because the user type is an int, but the insert statement is
      # providing text
      _id = uuid.uuid4()
      stmt = """
            INSERT INTO simple_table (id, number)
            VALUES ({id}, {{user_number: 'uh oh....this is not a number'}});
         """.format(id=_id)
      with self.assertRaisesRegexp(ProgrammingError, 'field user_number is not of type int'):
        cursor.execute(stmt)

      # let's check the rowcount and make sure the data
      # didn't get inserted when the exception asserted above was thrown
      stmt = """
            SELECT * FROM simple_table;
         """
      cursor.execute(stmt)
      self.assertEqual(0, cursor.rowcount)

    @since('2.1')
    def test_dropping_user_types(self):
      """
      Tests that a type cannot be dropped when in use, and otherwise can be dropped.
      """
      cluster = self.cluster
      cluster.populate(3).start()
      node1, node2, node3 = cluster.nodelist()
      cursor = self.cql_connection(node1).cursor()
      self.create_ks(cursor, 'user_type_dropping', 2)

      stmt = """
            CREATE TYPE simple_type (
            user_number int
            )
         """
      cursor.execute(stmt)

      stmt = """
            CREATE TABLE simple_table (
            id uuid PRIMARY KEY,
            number simple_type
            )
         """
      cursor.execute(stmt)

      _id = uuid.uuid4()
      stmt = """
            INSERT INTO simple_table (id, number)
            VALUES ({id}, {{user_number: 1}});
         """.format(id=_id)
      cursor.execute(stmt)

      stmt = """
            DROP TYPE simple_type;
         """
      with self.assertRaisesRegexp(ProgrammingError, 'Cannot drop user type simple_type as it is still used by table user_type_dropping.simple_table'):
        cursor.execute(stmt)

      # now that we've confirmed that a user type cannot be dropped while in use
      # let's remove the offending table

      # TODO: uncomment below after CASSANDRA-6472 is resolved
      # and add another check to make sure the table/type drops succeed
      # stmt = """
      #       DROP TABLE simple_table;
      #    """.format(id=_id)
      #
      # cursor.execute(stmt)
      # stmt = """
      #       DROP TYPE simple_type;
      #    """
      # cursor.execute(stmt)

    @since('2.1')
    def test_nested_user_types(self):
        """Tests user types within user types"""
        cluster = self.cluster
        cluster.populate(3).start()
        node1,node2,node3 = cluster.nodelist()
        cursor = self.cql_connection(node1).cursor()
        self.create_ks(cursor, 'user_types', 2)
        
        #### Create a user type to go inside another one:
        stmt = """
              CREATE TYPE item (
              sub_one text,
              sub_two text,
              )
           """
        cursor.execute(stmt)

        #### Create a user type to contain the item:
        stmt = """
              CREATE TYPE container (
              stuff text,
              more_stuff item
              )
           """
        cursor.execute(stmt)

        ### Create a table that holds and item, a container, and a
        ### list of containers:
        stmt = """
              CREATE TABLE bucket (
               id uuid PRIMARY KEY,
               primary_item item,
               other_items container,
               other_containers list<container>
              )
           """
        cursor.execute(stmt)

        ### Insert some data:
        _id = uuid.uuid4()
        stmt = """
              INSERT INTO bucket (id, primary_item)
              VALUES ({id}, {{sub_one: 'test', sub_two: 'test2'}});
           """.format(id=_id)
        cursor.execute(stmt)

        stmt = """
              UPDATE bucket
              SET other_items = {{stuff: 'stuff', more_stuff: {{sub_one: 'one', sub_two: 'two'}}}}
              WHERE id={id};
           """.format(id=_id)
        cursor.execute(stmt)

        stmt = """
              UPDATE bucket
              SET other_containers = other_containers + [{{stuff: 'stuff2', more_stuff: {{sub_one: 'one_other', sub_two: 'two_other'}}}}]
              WHERE id={id};
           """.format(id=_id)
        cursor.execute(stmt)

        stmt = """
              UPDATE bucket
              SET other_containers = other_containers + [{{stuff: 'stuff3', more_stuff: {{sub_one: 'one_2_other', sub_two: 'two_2_other'}}}}, {{stuff: 'stuff4', more_stuff: {{sub_one: 'one_3_other', sub_two: 'two_3_other'}}}}]
              WHERE id={id};
           """.format(id=_id)
        cursor.execute(stmt)

        ### Generate some repetitive data and check it for it's contents:
        for x in xrange(50):

            ### Create row:
            _id = uuid.uuid4()
            stmt = """
              UPDATE bucket
              SET other_containers = other_containers + [{{stuff: 'stuff3', more_stuff: {{sub_one: 'one_2_other', sub_two: 'two_2_other'}}}}, {{stuff: 'stuff4', more_stuff: {{sub_one: 'one_3_other', sub_two: 'two_3_other'}}}}]
              WHERE id={id};
           """.format(id=_id)
            cursor.execute(stmt)
            
            ### Check it:
            stmt = """
              SELECT other_containers from bucket WHERE id={id}
            """.format(id=_id)
            cursor.execute(stmt)

            try:
                items = cursor.fetchone()[0]
            except TypeError:
                print stmt
                raise
            print items
            self.assertEqual(len(items), 2)
            # Item 1:
            self.assertIn('stuff3', items[0])
            self.assertIn('one_2_other', items[0])
            self.assertIn('two_2_other', items[0])
            # Item 2:
            self.assertIn('stuff4', items[1])
            self.assertIn('one_3_other', items[1])
            self.assertIn('two_3_other', items[1])
            
