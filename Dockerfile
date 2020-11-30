FROM python:3.8
COPY ./Makefile ./Makefile
RUN make install
EXPOSE 80

CMD [ "uwsgi", "/app/config.yml" ]
