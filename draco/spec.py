'''
Tasks, Encoding, and Query helper classes for draco.
'''

import json
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Union

import agate
from agate.table import Table
from clyngor.answers import Answers


class Field():

    def __init__(self, name: str, ty: str, cardinality: int, entropy: Optional[float] = None) -> None:
        self.name = name

        # column data type, should be a string represented type,
        # one of ('string', 'number', 'datetime', 'date', 'boolean')
        self.ty = ty

        self.cardinality = cardinality
        self.entropy = entropy

    @staticmethod
    def from_obj(obj: Dict[str, str]):
        ''' Build a field from a field represented as a dictionary. '''
        return Field(obj['name'], obj['type'], int(obj['cardinality']), float(obj.get('entropy')))

    def to_asp(self) -> str:
        asp_str = f'fieldtype({self.name},{self.ty}).\n'
        asp_str += f'cardinality({self.name},{self.cardinality}).\n'
        if self.entropy is not None:
            # asp only supports integers
            asp_str += f'entropy({self.name},{int(self.entropy * 10)}).\n'
        return asp_str


class Data():

    @staticmethod
    def from_obj(obj: Dict[str, str], path_prefix: Optional[str] = None) -> 'Data':
        ''' Build a data object from a dict-represented
            Vega-Lite object represting data'''
        if 'url' in obj:
            # load data from url
            file_path = obj['url']
            if path_prefix is not None:
                file_path = os.path.join(path_prefix, file_path)
            return Data.from_csv(file_path)
        else:
            # a dict represented data already included in the file
            return Data.from_agate_table(agate.Table.from_object(obj['values']))

    @staticmethod
    def from_csv(filename: str) -> 'Data':
        ''' load data form a csv file '''
        table = agate.Table.from_csv(filename)
        dt = Data.from_agate_table(table)
        dt.url = filename
        return dt

    @staticmethod
    def from_agate_table(agate_table: Table) -> 'Data':
        ''' Create a Data object from an agate table,
            data content and datatypes are based on how agate interprets them
        '''
        fields: List[Field] = []

        for i in range(len(agate_table.column_names)):
            name = agate_table.column_names[i]
            agate_type = agate_table.column_types[i]
            type_name = 'string'
            if isinstance(agate_type, agate.Text):
                type_name = 'string'
            elif isinstance(agate_type, agate.Number):
                type_name = 'number'
            elif isinstance(agate_type, agate.Boolean):
                type_name = 'boolean'
            elif isinstance(agate_type, agate.Date):
                type_name = 'date'
            elif isinstance(agate_type, agate.DateTime):
                type_name = 'date' # take care!
            cardinality = len(set(agate_table.columns.get(name)))
            fields.append(Field(name, type_name, cardinality))

        # store the table into a dict
        content = []
        for row in agate_table.rows:
            row_obj = {}
            for j, c in enumerate(row):
                row_obj[fields[j].name] = str(c)
            content.append(row_obj)
        return Data(fields, len(agate_table), content=content)

    def __init__(self, fields: Iterable[Field], size: int, content: Optional[Iterable[Any]] = None, url: Optional[str] = None) -> None:
        self.fields = fields
        self.size = size
        self.content = content
        self.url = url

    def __len__(self):
        return self.size

    def to_vegalite(self) -> Dict[str, Any]:
        if self.url :
            return {'url': self.url}
        else:
            return {'values': self.content}

    def to_asp(self) -> str:
        return f'data_size({len(self)}).\n\n' + '\n'.join([x.to_asp() for x in self.fields])


class Encoding():

    # keep track of what encodings we have already generated
    encoding_cnt = 0

    @staticmethod
    def gen_encoding_id() -> str:
        enc = f'e{Encoding.encoding_cnt}'
        Encoding.encoding_cnt += 1
        return enc

    @staticmethod
    def from_obj(obj: Dict[str, Union[str, Dict]]) -> 'Encoding':
        ''' load encoding from a dict object representing the spec content
            Args:
                obj: a dict object representing channel encoding
            Returns:
                an encoding object
        '''

        scale = obj.get('scale')

        binning = obj.get('bin')
        if binning and isinstance(binning, dict):
            binning = binning['maxbins']

        return Encoding(
            obj.get('channel'),
            obj.get('field'),
            obj.get('type'),
            obj.get('aggregate'),
            binning,
            scale.get('type') == 'log' if scale else None,
            scale.get('zero') if scale else None)

    @staticmethod
    def parse_from_answer(encoding_id: str, encoding_props: Dict) -> 'Encoding':
        return Encoding(
            encoding_props['channel'],
            encoding_props.get('field'),
            encoding_props['type'],
            encoding_props.get('aggregate'),
            encoding_props.get('bin'),
            encoding_props.get('log_scale'),
            encoding_props.get('zero'),
            encoding_id)

    def __init__(self, channel: Optional[str] = None, field: Optional[str] = None, ty: Optional[str] = None, aggregate: Optional[str] = None, binning: Optional[Union[int, bool]] = None, log_scale: Optional[bool] = None, zero: Optional[bool] = None, idx: Optional[str] = None) -> None:
        self.channel = channel
        self.field = field
        self.ty = ty
        self.aggregate = aggregate
        self.binning = binning
        self.log_scale = log_scale
        self.zero = zero
        self.id = idx if idx is not None else Encoding.gen_encoding_id()

    def to_vegalite(self):
        encoding = {
            'scale': {}
        }

        if self.field:
            encoding['field'] = self.field
        if self.ty:
            encoding['type'] = self.ty
        if self.aggregate:
            encoding['aggregate'] = self.aggregate
        if self.binning:
            encoding['bin'] = {'maxbins' : int(self.binning)}
        if self.log_scale:
            encoding['scale']['type'] = 'log'
        encoding['scale']['zero'] = False if self.zero == None else self.zero

        return encoding

    def to_asp(self) -> str:
        constraints = [f'encoding({self.id}).']

        def _constraint(prop: str, value: str) -> str:
            if value == False:
                return f':- {prop}({self.id},_).'
            if value == True or value == '?':
                return f':- not {prop}({self.id},_).'
            else:
                return f'{prop}({self.id},{value}).'

        if self.channel is not None:
            constraints.append(_constraint('channel', self.channel))

        if self.field is not None:
            constraints.append(_constraint('field', self.field))

        if self.ty is not None:
            constraints.append(_constraint('type', self.ty))

        if self.aggregate is not None:
            constraints.append(_constraint('aggregate', self.aggregate))

        if self.binning is not None:
            constraints.append(_constraint('bin', self.binning))


        if self.log_scale == True:
            constraints.append(f'log({self.id}).')
        if self.log_scale == False:
            constraints.append(f':- log({self.id}).')

        if self.zero == True:
            constraints.append(f'zero({self.id}).')
        if self.zero == False:
            constraints.append(f':- zero({self.id}).')

        return  '\n'.join(constraints) + '\n'


class Query():

    def __init__(self, mark: str, encodings: Iterable[Encoding] = None) -> None:
        # channels include 'x', 'y', 'color', 'size', 'shape', 'text', 'detail'
        self.mark = mark
        self.encodings = encodings or []

    @staticmethod
    def from_obj(query_spec: Dict) -> 'Query':
        ''' Parse from a query object that uses a list for encoding. '''
        mark = query_spec.get('mark')
        encodings = map(Encoding.from_obj, query_spec.get('encoding', []))
        return Query(mark, encodings)

    @staticmethod
    def from_vegalite(full_spec: Dict) -> 'Query':
        ''' Parse from Vega-Lite spec that uses map for encoding. '''
        encodings: List[Encoding] = []

        for channel, enc in full_spec.get('encoding', {}).items():
            enc['channel'] = channel
            encodings.append(Encoding.from_obj(enc))

        return Query(full_spec['mark'], encodings)

    @staticmethod
    def parse_from_answer(clyngor_answer: Answers) -> 'Query':
        encodings: List[Encoding] = []
        mark = None

        raw_encoding_props: Dict = defaultdict(dict)

        for (head, body), in clyngor_answer:
            if head == 'mark':
                mark = body[0]
            else:
                # collect encoding properties
                raw_encoding_props[body[0]][head] = body[1] if len(body) > 1 else True

        # generate encoding objects from each collected encodings
        for k, v in raw_encoding_props.items():
            encodings.append(Encoding.parse_from_answer(k, v))

        return Query(mark, encodings)

    def to_vegalite(self):
        query = {}
        query['mark'] = self.mark
        query['encoding'] = {}
        for e in self.encodings:
            query['encoding'][e.channel] = e.to_vegalite()
        return query

    def to_asp(self) -> str:
        # the asp constraint comes from both mark and encodings

        prog = ''

        if self.mark:
            prog += f'mark({self.mark}).\n\n'

        prog += '\n'.join(map(lambda e: e.to_asp(), self.encodings))
        return prog


class Task():

    def __init__(self, data: Data, query: Query, cost: Optional[int] = None, violations: Optional[Dict[str, int]] = None) -> None:
        self.data = data
        self.query = query
        self.violations = violations
        self.cost = cost

    @staticmethod
    def from_obj(query_spec, data_dir: Optional[str]) -> 'Task':
        data = Data.from_obj(query_spec['data'], path_prefix=data_dir)

        query = Query.from_obj(query_spec)

        return Task(data, query)

    def to_vegalite(self):
        ''' generate a vegalite spec from the object '''
        result = self.query.to_vegalite()
        result['data'] = self.data.to_vegalite()
        result['$schema'] = 'https://vega.github.io/schema/vega-lite/v2.0.json'
        return result

    def to_vegalite_json(self) -> str:
        ''' generate a vegalite json file form the object '''
        return json.dumps(self.to_vegalite(), sort_keys=True, indent=4)

    def to_asp(self) -> str:
        ''' generate asp constraints from the object '''
        asp_str = '% ====== Data definitions ======\n'
        asp_str += self.data.to_asp() + '\n\n'
        asp_str += '% ====== Query constraints ======\n'
        asp_str += self.query.to_asp()
        return asp_str
