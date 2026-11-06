#!/usr/bin/env python3
"""Build a private Raimo API patch; never print or commit the generated definition."""
from __future__ import annotations
import argparse,copy,json
from pathlib import Path
import yaml
ENDPOINT='POST /internal/normal-answer-v2'
STRUCTURED_INSTRUCTION='以下の回答ルールと根拠を守り、出力全体を厳密なJSONオブジェクト1個だけにしてください。Markdownコードフェンスは禁止。形式は {"answer":"日本語の回答本文","used_sources":{"comment_ids":["実際に使ったcomment_id"],"chunk_keys":["実際に使ったchunk_key"]}}。answerに通常の回答を書くこと。used_sourcesには本文の根拠に使った提示情報のIDだけを文字列で入れ、未使用IDや存在しないIDを追加しない。該当するIDがなければ空配列。JSONの内部以外に説明を書かない。\n\n'
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
 quality='answer文字列の中では、通常回答と同じMarkdownの見出し・箇条書きを使ってください。JSON形式を理由に回答本文を短縮しないでください。質問に関係する独立した工夫・具体例・契約上の制約・注意点・リスクを参考情報から幅広く拾い、項目を分けて十分詳しく答えてください。JSON全体をコードフェンスで囲むことだけは禁止です。 '
 prefix=(STRUCTURED_INSTRUCTION+quality).replace('\n',' ').replace('\\','\\\\').replace("'","\\'")
 prompt['calculate']['expression']="'"+prefix+expression[1:]
 answer=copy.deepcopy(next(s for s in steps if s.get('as')=='answer'));answer['llm']['prompt']='computed.promptText';answer['as']='structuredAnswer';selected.append(answer)
 route={'name':'generateNormalAnswerV2','endpoint':ENDPOINT,'steps':selected,'output':{'response':'llm.structuredAnswer','relatedComments':'fetched.relatedCommunityComments','relatedLessonComments':'fetched.relatedLessonComments','relatedChunks':'fetched.relatedChunks'}}
 routes[:]=[r for r in routes if r.get('endpoint')!=ENDPOINT];routes.append(route);return d
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);a=parser.parse_args()
 if a.source.resolve()==a.output.resolve():parser.error('source and output must differ')
 a.output.write_text(yaml.safe_dump(patch(yaml.safe_load(a.source.read_text())),allow_unicode=True,sort_keys=False,width=100000));a.output.chmod(0o600)
 print('Private API patch written; existing endpoints preserved')
