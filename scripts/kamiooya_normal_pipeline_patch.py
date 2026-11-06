#!/usr/bin/env python3
"""Build a private Raimo API patch; never print or commit the generated definition."""
from __future__ import annotations
import argparse,copy,json
from pathlib import Path
import yaml
ENDPOINT='POST /internal/normal-answer-v2'
def validate_output_path(path):
 resolved=path.resolve()
 if any((parent/'.git').exists() for parent in resolved.parents):raise ValueError('generated definition must stay outside Git repositories')
 for cloud in [Path.home()/'Library/CloudStorage',Path.home()/'Library/Mobile Documents']:
  if resolved.is_relative_to(cloud):raise ValueError('generated definition must stay outside cloud-sync folders')
CITATION_INSTRUCTION='以下の通常回答の指示と構成をそのまま守り、Markdownの見出し・箇条書きを使って回答してください。回答の各項目で使った参考情報の実際のIDを、文末に〔コメントID:123〕または〔チャンクID:実際のchunk_key〕という機械読取タグで添えてください。IDは提示されたJSON内のcomment_id/chunk_keyをそのまま使い、架空のIDや連番に置き換えないでください。複数の根拠を使った項目にはそれぞれのタグを添えてください。タグは画面側で出典番号に変換します。タグの追加を理由に本文の情報量・具体例・注意点を削らないでください。JSONオブジェクトや別の根拠一覧は出力せず、通常の回答本文をそのまま書いてください。 '

def patch(document):
 d=copy.deepcopy(document);routes=d['api'];old=next(r for r in routes if r.get('endpoint')=='POST /chat-sessions/{id}/messages');steps=old['steps']
 if [s.get('as') for s in steps if 'llm' in s]!=['keyword','answer','usedSources']:raise ValueError('unexpected normal pipeline; review before patching')
 guard=steps[0]
 if 'check' not in guard or '__gateway_secret' not in json.dumps(guard):raise ValueError('missing internal server guard')
 selected=[]
 for s in steps:
  if 'check' in s or s.get('as') in ['keyword','relatedCommunityComments','relatedLessonComments','relatedChunks','promptText']:selected.append(copy.deepcopy(s))
 prompt=next(s for s in selected if s.get('as')=='promptText')
 expression=prompt['calculate']['expression']
 if not expression.startswith("'"):raise ValueError('unexpected prompt literal syntax')
 # Raimo calculations support its existing single-quoted concatenation form;
 # keep the original expression rather than chaining computed values.
 quality='複数の工夫や注意点を尋ねられた場合は、参考にある関連する独立論点を省かないでください。特に契約上の制約、証拠の残し方、施工上のリスク、材料・工期、資金調達について参考に関連記述があるときは、それぞれ項目を分けてください。質問と無関係な論点を足したり、参考にない事実を補ったりせず、各項目は簡潔にまとめてください。 '
 prefix=(CITATION_INSTRUCTION+quality).replace('\n',' ').replace('\\','\\\\').replace("'","\\'")
 prompt['calculate']['expression']="'"+prefix+expression[1:]
 answer=copy.deepcopy(next(s for s in steps if s.get('as')=='answer'));answer['llm']['prompt']='computed.promptText';answer['as']='structuredAnswer';selected.append(answer)
 route={'name':'generateNormalAnswerV2','endpoint':ENDPOINT,'steps':selected,'output':{'response':'llm.structuredAnswer','relatedComments':'fetched.relatedCommunityComments','relatedLessonComments':'fetched.relatedLessonComments','relatedChunks':'fetched.relatedChunks'}}
 routes[:]=[r for r in routes if r.get('endpoint')!=ENDPOINT];routes.append(route);return d
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);a=parser.parse_args()
 if a.source.resolve()==a.output.resolve():parser.error('source and output must differ')
 validate_output_path(a.output)
 a.output.write_text(yaml.safe_dump(patch(yaml.safe_load(a.source.read_text())),allow_unicode=True,sort_keys=False,width=100000));a.output.chmod(0o600)
 print('Private API patch written; existing endpoints preserved')
