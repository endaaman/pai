## AI

### client

```
$ pipenv install

$ pipenv run dev
# or
$ make client
```

### server

```
$ npm i

$ npm run dev
# or
$ make server
```

### client

- サーバー状態の表示
  - 処理中のアイテムの表示
  - 手動再接続

- 解析ボタンを押したら、画像を固定する
- 処理中ぐるぐるを表示
- ぐるぐるの間に
  - カメラを再び動かせるようにするボタン
  - キャンセルボタン

### server

- 画像がアップロードされたら、画像をモデルに流す
- 処理中であることをstatusに示す
- 処理中はアップロードを受け付けない
- 処理が終わったらstatusに示す
