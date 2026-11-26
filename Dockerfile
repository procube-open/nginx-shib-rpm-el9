FROM almalinux/9-base

RUN groupadd -g 111 builder \
    && useradd -g builder -u 111 builder
ENV HOME=/home/builder
WORKDIR ${HOME}

ENV NGINX_VERSION=1.30.7-1.el9
RUN dnf -y update \
    && dnf -y install gcc make wget tar gzip patch rpm-build rpmdevtools \
        systemd-devel openssl-devel zlib-devel pcre2-devel \
        perl-devel perl-ExtUtils-Embed libxslt-devel gd-devel which \
    && dnf clean all

COPY core.patch shibboleth.patch nginx.spec.patch nginx.conf.patch /tmp/buffer/

USER builder
RUN mkdir -p ${HOME}/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS} ${HOME}/srpms \
    && echo "%_topdir ${HOME}/rpmbuild" > ${HOME}/.rpmmacros \
    && cp /tmp/buffer/* ${HOME}/rpmbuild/SOURCES/ \
    && wget --no-verbose -O ${HOME}/srpms/nginx.src.rpm https://nginx.org/packages/centos/9/SRPMS/nginx-${NGINX_VERSION}.ngx.src.rpm \
    && rpm -ivh ${HOME}/srpms/nginx.src.rpm \
    && cd ${HOME}/rpmbuild/SOURCES \
    && wget --no-verbose -O ngx_devel_kit-0.3.4.tar.gz https://github.com/vision5/ngx_devel_kit/archive/refs/tags/v0.3.4.tar.gz \
    && wget --no-verbose -O lua-nginx-module-0.10.31.tar.gz https://github.com/openresty/lua-nginx-module/archive/refs/tags/v0.10.31.tar.gz \
    && wget --no-verbose -O luajit2-2.1-20261117.tar.gz https://github.com/openresty/luajit2/archive/refs/tags/v2.1-20261117.tar.gz \
    && wget --no-verbose -O lua-resty-core-0.1.34rc3.tar.gz https://github.com/openresty/lua-resty-core/archive/refs/tags/v0.1.34rc3.tar.gz \
    && wget --no-verbose -O lua-resty-lrucache-0.15.tar.gz https://github.com/openresty/lua-resty-lrucache/archive/refs/tags/v0.15.tar.gz \
    && wget --no-verbose -O nginx-http-shibboleth-2.0.2.tar.gz https://github.com/nginx-shib/nginx-http-shibboleth/archive/refs/tags/v2.0.2.tar.gz \
    && wget --no-verbose -O headers-more-nginx-module-0.42.tar.gz https://github.com/openresty/headers-more-nginx-module/archive/refs/tags/v0.42.tar.gz \
    && wget --no-verbose -O nginx_ajp_module-0.3.6.tar.gz https://github.com/dvershinin/nginx_ajp_module/archive/refs/tags/v0.3.6.tar.gz \
    && patch < nginx.conf.patch \
    && cd ${HOME}/rpmbuild/SPECS \
    && patch -p1 nginx.spec < ../SOURCES/nginx.spec.patch

CMD ["/usr/bin/rpmbuild", "-bb", "rpmbuild/SPECS/nginx.spec"]
