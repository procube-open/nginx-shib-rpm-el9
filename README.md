# nginx-shib-rpm-el9

EL9 向け nginx RPM のビルド環境です。nginx 1.30.7 に Shibboleth
FastCGI authorizer、OpenResty LuaJIT2、lua-nginx-module、NDK、
headers-more、AJP を組み込みます。LuaJIT2 と対応する lua-resty-core、
lua-resty-lrucache は RPM 内に同梱します。Shibboleth SP 本体と FastCGI
authorizer は別途必要です。
旧 jdomain・sticky のソースとパッチは履歴参照用であり、ビルドには使用しません。

## ビルド

```sh
docker build -t nginx-shib-rpm-el9 .
mkdir -p RPMS
sudo chown 111:111 RPMS
docker run --rm -v "$(pwd)/RPMS:/home/builder/rpmbuild/RPMS" nginx-shib-rpm-el9
```

生成された nginx RPM を EL9 の検証環境でインストールし、既存設定を適用した
`nginx -t` と実際の認証・アプリケーション動作を確認してから展開してください。
既存の `%config(noreplace)` 設定は上書きされないため、RPM 更新だけでは下記の
設定変更は反映されません。
生成 RPM は nginx.org の EL9 パッケージと同じ Epoch 2 を使い、リリース名に
`.procube` を付けています。nginx.org の新しい RPM で上書きすると追加モジュールが
失われるため、更新元を管理してください。

CI では RPM をクリーンな EL9 にインストールし、LuaJIT、模擬 FastCGI
authorizer、AJP、標準 sticky、動的 DNS の動作を確認します。ローカルでも
ビルド後に実行できます。

```sh
docker run --rm -v "$(pwd)/RPMS:/rpms:ro" -v "$(pwd)/tests:/tests:ro" \
  almalinux/9-base \
  bash -ec 'dnf -y install /rpms/x86_64/nginx-1.*.rpm && python3 /tests/integration.py'
```

## 移行上の注意

* nginx 1.30 の標準 sticky は旧 nginx-sticky-module-ng と構文や Cookie 値が
  異なります。既存の Cookie は引き継がれず、既存セッションの接続先が変わる
  可能性があります。旧 `text=raw` のポートを除く独自のルーティング動作や
  `no_fallback` 等は自動的に再現されません。運用中の設定を確認してください。

  ```nginx
  upstream backend {
      server 192.0.2.1:8080;
      server 192.0.2.2:8080;
      sticky cookie route path=/;
  }
  ```

* `jdomain` は含まれません。標準の動的 DNS 解決には共有メモリ `zone`、
  `resolver` と `server ... resolve` が必要です。`interval`、`max_ips`、
  `retry_off` は直接対応しないため、DNS TTL、再試行と障害時の動作を検証して
  ください。以下の DNS サーバーとポートは環境に合わせて変更してください。

  ```nginx
  resolver 192.0.2.53 valid=30s;
  upstream backend {
      zone backend 64k;
      server backend.example.com:8080 resolve;
  }
  ```

* LuaJIT は Lua 5.1 と互換性がありますが、実装やバイトコード形式は同一では
  ありません。既存の Lua スクリプト、C 拡張、事前コンパイル済みバイトコードを
  検証し、必要に応じて再ビルドしてください。
* nginx の新しいバージョンでは upstream proxy の既定値が HTTP/1.1 に変わって
  います。旧動作が必要な場合は `proxy_http_version 1.0;` を明示してください。
* Shibboleth の既存パッチによる複数の `Set-Cookie` と `$remote_user` の扱いは
  維持しています。属性ヘッダーの偽装防止設定を含め、実際の SP と IdP で
  ログイン・ログアウトを検証してください。

標準機能の詳細: [動的 DNS 解決](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server)、
[sticky](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#sticky)。
