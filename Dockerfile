FROM almalinux/9-base
MAINTAINER "Shigeki Kitamura" <kitamura@procube.jp>
RUN groupadd -g 111 builder
RUN useradd -g builder -u 111 builder
ENV HOME /home/builder
WORKDIR ${HOME}
ENV NGINX_VERSION "1.21.6-1.el9"
RUN dnf -y update \
    && dnf -y install unzip wget sudo lsof openssh-clients telnet bind-utils tar tcpdump vim initscripts \
        gcc openssl-devel zlib-devel pcre-devel rpmdevtools make \
        perl-devel perl-ExtUtils-Embed libxslt-devel gd-devel which \
        ncurses-devel readline-devel git
RUN dnf -y install almalinux-release-devel \
    && dnf -y install redhat-lsb-core
#RUN cd /tmp && git clone https://github.com/openresty/luajit2.git \
#    && cd luajit2 && make && make install
#RUN dnf -y install epel-release \
#    && dnf -y install luajit luajit-devel
#ENV LUAJIT_INC /usr/include/luajit-2.1/
#ENV LUAJIT_LIB /usr/lib64/
RUN mkdir -p /tmp/requires \
    && cd /tmp/requires/ \
    && wget --no-verbose -O /tmp/requires/lua.tar.gz https://github.com/procube-open/lua51-el9/releases/download/1.0.0/lua51-el9.tar.gz \
    && tar xvzf lua.tar.gz \
    && cd RPMS/x86_64/ \
    && rpm -ivh lua-5.*.rpm lua-devel-5.*.rpm
RUN mkdir -p /tmp/buffer
COPY core.patch shibboleth.patch nginx.spec.patch nginx.conf.patch jdomain_http.patch /tmp/buffer/
USER builder
RUN mkdir -p ${HOME}/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
RUN echo "%_topdir %(echo ${HOME})/rpmbuild" > ${HOME}/.rpmmacros
RUN cp /tmp/buffer/* ${HOME}/rpmbuild/SOURCES/
RUN wget --no-verbose -O rpmbuild/SOURCES/ngx_devel_kit-0.3.3.tar.gz https://github.com/vision5/ngx_devel_kit/archive/refs/tags/v0.3.3.tar.gz
#RUN wget --no-verbose -O rpmbuild/SOURCES/lua-nginx-module-0.10.13.tar.gz https://github.com/openresty/lua-nginx-module/archive/refs/tags/v0.10.13.tar.gz
RUN wget --no-verbose -O rpmbuild/SOURCES/lua-nginx-module-0.10.13.tar.gz https://github.com/openresty/lua-nginx-module/archive/refs/tags/v0.10.13.tar.gz
#RUN wget --no-verbose -O rpmbuild/SOURCES/nginx-goodies-nginx-sticky-module-ng-08a395c66e42.tar.gz https://bitbucket.org/nginx-goodies/nginx-sticky-module-ng/get/08a395c66e42.tar.gz
RUN wget --no-verbose -O rpmbuild/SOURCES/nginx-http-shibboleth-2.0.2.tar.gz https://github.com/nginx-shib/nginx-http-shibboleth/archive/v2.0.2.tar.gz
RUN wget --no-verbose -O rpmbuild/SOURCES/headers-more-nginx-module-0.38.tar.gz https://github.com/openresty/headers-more-nginx-module/archive/v0.38.tar.gz
RUN wget --no-verbose -O rpmbuild/SOURCES/nginx_ajp_module-0.3.3.tar.gz https://github.com/dvershinin/nginx_ajp_module/archive/refs/tags/v0.3.3.tar.gz


# ADD https://github.com/yaoweibin/nginx_ajp_module/archive/v0.3.0.tar.gz rpmbuild/SOURCES/nginx_ajp_module-0.3.0.tar.gz
# this cause
# /root/rpmbuild/BUILD/nginx-1.10.1/nginx_ajp_module-0.3.0/ngx_http_ajp_module.c: In function 'ngx_http_ajp_store':
# /root/rpmbuild/BUILD/nginx-1.10.1/nginx_ajp_module-0.3.0/ngx_http_ajp_module.c:467:30: error: comparison between pointer and integer [-Werror]
#      if (alcf->upstream.cache != NGX_CONF_UNSET_PTR
# Last Commits for master branch on Feb 28, 2015
#COPY nginx_ajp_module-master.tar.gz rpmbuild/SOURCES/nginx_ajp_module-master.tar.gz
# Latest commit 1a92c67  on 19 Jul 2017


COPY ngx_upstream_jdomain-master.tar.gz  rpmbuild/SOURCES/ngx_upstream_jdomain-master.tar.gz
RUN mkdir ${HOME}/srpms \
    && cd srpms \
    && wget --no-verbose -O nginx.src.rpm https://nginx.org/packages/mainline/centos/9/SRPMS/nginx-${NGINX_VERSION}.ngx.src.rpm \
    && rpm -ivh nginx.src.rpm
RUN cd rpmbuild/SPECS \
    && patch -p 1 nginx.spec < ../SOURCES/nginx.spec.patch
RUN cd rpmbuild/SOURCES \
    && patch < nginx.conf.patch
CMD ["/usr/bin/rpmbuild","-bb","rpmbuild/SPECS/nginx.spec"]
