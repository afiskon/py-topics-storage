create table users(
  id serial not null primary key,
  login varchar(128) not null,
  password char(64) not null, -- sha256(salt + sha256(passowrd))
  salt char(8) not null,
  email varchar(128) not null,
  homepage varchar(128) not null, -- blog, github, twitter, habr, etc...
  name varchar(128) not null,
  is_active boolean not null,
  created timestamp not null
);

insert into users (login, password, salt, email, homepage, name, is_active, created)
values(
  'admin',
  'd16ed3847bb0c377371f6ade2471d28e61f779cb261b28a963c0c539615fb8d6', -- password: admin
  '__salt__',
  'admin@example.com',
  'http://example.ru',
  'Mr Admin',
  true,
  now()
);

create table themes(
  id serial not null primary key,
  rev int not null,
  title varchar(128) not null, -- required
  url varchar(128) not null,   -- optional
  description text not null,   -- optional
  created timestamp not null,
  created_by int references users(id) not null,
  updated timestamp not null,
  updated_by int references users(id) not null,
  current_at timestamp not null,
  discussed_at timestamp not null,
  status char not null, -- 'c': current, 'r': regular, 'd': discussed
  priority int not null -- 50: highest, 40: high, 30: medium, 20: low, 10: lowest
);

create table responsibles(
  uid int references users(id) not null,
  tid int references themes(id) not null,
  constraint uid_tid_unique unique(uid, tid)
);

create table invites(
  code char(16) not null primary key,
  email varchar(128) not null,
  created timestamp not null,
  created_by int references users(id) not null,
  used_by int references users(id) -- can by null
);

create table global(
  key varchar(128),
  value varchar(128)
);

insert into global values ( 'recording_start_time', now() :: text );
