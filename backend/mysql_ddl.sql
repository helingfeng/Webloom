-- fishcode 平台 MySQL 建表 DDL（由 scripts/gen_mysql_ddl.py 从 SQLAlchemy 模型生成，勿手工改列）
-- 改动模型后需重新执行：cd backend && python scripts/gen_mysql_ddl.py
-- 使用前先建库（表已显式声明 utf8mb4）：
-- CREATE DATABASE fishcode DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;


CREATE TABLE `collector_tasks`
(
    `id`            bigint unsigned  NOT NULL AUTO_INCREMENT COMMENT '主键',
    `collector_id`  bigint unsigned  NOT NULL COMMENT '发布接口 ID',
    `app_id`        bigint unsigned  NOT NULL COMMENT '调用应用 ID',
    `execution_id`  bigint unsigned  NOT NULL COMMENT '执行记录 ID',
    `request_key`   varchar(128)     NULL COMMENT '调用方幂等键',
    `request_hash`  varchar(64)      NOT NULL COMMENT '幂等请求摘要',
    `created_at`    datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提交时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY (`execution_id`) USING BTREE,
    UNIQUE KEY `uq_collector_task_request` (`app_id`, `request_key`) USING BTREE,
    KEY `ix_collector_tasks_app_id` (`app_id`) USING BTREE,
    KEY `ix_collector_tasks_collector_id` (`collector_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='采集任务持久归属与幂等记录';

CREATE TABLE `collectors`
(
    `id`           bigint unsigned      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `slug`         varchar(80)          NOT NULL COMMENT '稳定接口标识',
    `name`         varchar(255)         NOT NULL COMMENT '接口名称',
    `description`  text                 NOT NULL COMMENT '面向调用方的说明',
    `script_id`    bigint unsigned      NOT NULL COMMENT '绑定脚本 ID',
    `app_ids`      json                 NOT NULL COMMENT '授权应用 ID 列表',
    `enabled`      tinyint(1) unsigned  NOT NULL DEFAULT '1' COMMENT '是否发布',
    `archived`     tinyint(1) unsigned  NOT NULL DEFAULT '0' COMMENT '是否已移除（保留历史任务）',
    `created_at`   datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY (`slug`) USING BTREE,
    KEY `ix_collectors_script_id` (`script_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='发布的采集接口';

CREATE TABLE `data_views`
(
    `id`             bigint unsigned      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`           varchar(255)         NOT NULL COMMENT '视图名称',
    `slug`           varchar(64)          NOT NULL COMMENT '对外取数标识（GET /api/data/{slug}）',
    `datasource_id`  bigint unsigned      NOT NULL COMMENT '逻辑关联数据源 ID（无外键）',
    `database`       varchar(255)         NOT NULL DEFAULT '' COMMENT '执行库（空为数据源默认库）',
    `sql`            text                 NOT NULL COMMENT '只读 SQL',
    `description`    text                 NOT NULL COMMENT '描述',
    `enabled`        tinyint(1) unsigned  NOT NULL DEFAULT '1' COMMENT '是否启用：1-启用/0-停用',
    `created_at`     datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`     datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `ix_data_views_datasource_id` (`datasource_id`) USING BTREE,
    UNIQUE KEY `ix_data_views_slug` (`slug`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据视图表（数据源 + 只读 SQL 对外取数）';

CREATE TABLE `datasources`
(
    `id`           bigint unsigned  NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`         varchar(255)     NOT NULL COMMENT '数据源名称',
    `host`         varchar(255)     NOT NULL COMMENT '主机',
    `port`         int              NOT NULL DEFAULT 3306 COMMENT '端口',
    `user`         varchar(255)     NOT NULL COMMENT '用户名',
    `password`     varchar(255)     NOT NULL DEFAULT '' COMMENT '密码（明文存储，接口不回传）',
    `database`     varchar(255)     NOT NULL DEFAULT '' COMMENT '默认库',
    `description`  text             NOT NULL COMMENT '描述',
    `created_at`   datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='外部数据源表';

CREATE TABLE `executions`
(
    `id`           bigint unsigned  NOT NULL AUTO_INCREMENT COMMENT '主键',
    `target_type`  varchar(20)      NOT NULL COMMENT '目标类型：script（兼容历史执行类型）',
    `target_id`    bigint unsigned  NOT NULL COMMENT '目标 ID',
    `mode`         varchar(20)      NOT NULL COMMENT '执行模式：manual-真实入参/mock-按输入定义生成 mock',
    `inputs`       json             NOT NULL COMMENT '输入参数 JSON',
    `status`       varchar(20)      NOT NULL DEFAULT 'pending' COMMENT '状态：pending/running/success/failed/timeout',
    `logs`         text             NOT NULL COMMENT '完整日志',
    `outputs`      json             NOT NULL COMMENT '输出结果 JSON',
    `started_at`   datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    `finished_at`  datetime         NULL COMMENT '结束时间',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='脚本执行记录表';

CREATE TABLE `global_variables`
(
    `id`           bigint unsigned      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`         varchar(255)         NOT NULL COMMENT '变量名',
    `value`        text                 NOT NULL COMMENT '变量值（前端列表打码显示）',
    `type`         varchar(50)          NOT NULL DEFAULT 'header' COMMENT '类型：header/variable/localStorage/cookie',
    `domain`       varchar(255)         NOT NULL DEFAULT '' COMMENT '绑定域名（空为对全部域名生效）',
    `enabled`      tinyint(1) unsigned  NOT NULL DEFAULT '1' COMMENT '是否启用：1-启用/0-禁用',
    `description`  text                 NOT NULL COMMENT '备注',
    `created_at`   datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='全局变量表';

CREATE TABLE `open_api_logs`
(
    `id`            bigint unsigned      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `app_id`        bigint unsigned      NULL COMMENT '应用 ID（认证失败为空）',
    `app_key`       varchar(64)          NOT NULL DEFAULT '' COMMENT '调用方 App Key',
    `path`          varchar(255)         NOT NULL DEFAULT '' COMMENT '请求路径',
    `method`        varchar(10)          NOT NULL DEFAULT '' COMMENT 'HTTP 方法',
    `status_code`   int                  NOT NULL DEFAULT 0 COMMENT '响应状态码',
    `success`       tinyint(1) unsigned  NOT NULL DEFAULT '1' COMMENT '是否成功：1-成功/0-失败',
    `execution_id`  bigint unsigned      NULL COMMENT '关联执行 ID（采集触发）',
    `request_ip`    varchar(64)          NOT NULL DEFAULT '' COMMENT '调用方 IP',
    `detail`        text                 NOT NULL COMMENT '摘要/失败原因',
    `created_at`    datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `ix_open_api_logs_app_id` (`app_id`) USING BTREE,
    KEY `ix_open_api_logs_execution_id` (`execution_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='开放接口调用日志表（含认证失败记录）';

CREATE TABLE `open_apps`
(
    `id`           bigint unsigned      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`         varchar(255)         NOT NULL COMMENT '应用名称',
    `app_key`      varchar(64)          NOT NULL COMMENT '开放应用 App Key（调用方标识）',
    `app_secret`   varchar(128)         NOT NULL COMMENT 'App Secret（签名密钥）',
    `enabled`      tinyint(1) unsigned  NOT NULL DEFAULT '1' COMMENT '是否启用：1-启用/0-停用',
    `description`  text                 NOT NULL COMMENT '描述',
    `created_at`   datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `ix_open_apps_app_key` (`app_key`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='开放平台应用表（App Key + Secret 凭证）';

CREATE TABLE `query_history`
(
    `id`              bigint unsigned      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `datasource_id`   bigint unsigned      NOT NULL COMMENT '逻辑关联数据源 ID（无外键）',
    `database`        varchar(255)         NOT NULL DEFAULT '' COMMENT '执行库',
    `sql`             text                 NOT NULL COMMENT '执行的 SQL',
    `success`         tinyint(1) unsigned  NOT NULL DEFAULT '0' COMMENT '是否成功：1-成功/0-失败',
    `statement_type`  varchar(20)          NOT NULL DEFAULT 'query' COMMENT '语句类型：query/execute',
    `columns`         json                 NOT NULL COMMENT '结果列名 JSON',
    `rows`            json                 NOT NULL COMMENT '结果行 JSON（最多 200 行样本）',
    `row_count`       int                  NOT NULL DEFAULT 0 COMMENT '真实行数',
    `truncated`       tinyint(1) unsigned  NOT NULL DEFAULT '0' COMMENT '结果是否被截断：1-是/0-否',
    `affected_rows`   int                  NOT NULL DEFAULT 0 COMMENT '影响行数',
    `elapsed_ms`      int                  NOT NULL DEFAULT 0 COMMENT '耗时（毫秒）',
    `error`           text                 NULL COMMENT '错误信息',
    `created_at`      datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `ix_query_history_datasource_id` (`datasource_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SQL 执行历史表';

CREATE TABLE `scripts`
(
    `id`              bigint unsigned      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `workspace_id`    bigint unsigned      NULL COMMENT '逻辑归属 Workspace（无外键）',
    `name`            varchar(255)         NOT NULL COMMENT '脚本名称',
    `description`     text                 NOT NULL COMMENT '描述',
    `start_url`       text                 NOT NULL COMMENT '起始 URL',
    `inputs`          json                 NOT NULL COMMENT '输入参数定义 [{name,type,description,default,required}]，type 含 string/number/boolean/secret/header/cookie/localStorage',
    `outputs`         json                 NOT NULL COMMENT '输出定义 [{name,description}]',
    `code`            text                 NOT NULL COMMENT '用户 Playwright 代码片段',
    `inherit_global`  tinyint(1) unsigned  NOT NULL DEFAULT '1' COMMENT '是否继承全局变量：1-继承/0-不继承',
    `run_mode`        varchar(16)          NOT NULL DEFAULT 'manual' COMMENT '运行方式：manual-手动',
    `headless`        tinyint(1) unsigned  NOT NULL DEFAULT '1' COMMENT '是否无头运行：1-是/0-否',
    `created_at`      datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`      datetime             NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    KEY `ix_scripts_workspace_id` (`workspace_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='测试脚本表';

CREATE TABLE `skills`
(
    `id`               bigint unsigned  NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`             varchar(255)     NOT NULL COMMENT '技能名称',
    `description`      text             NOT NULL COMMENT '描述',
    `prompt_template`  text             NOT NULL COMMENT '提示词模板',
    `example_code`     text             NOT NULL COMMENT '示例代码',
    `example_inputs`   json             NOT NULL COMMENT '示例输入 JSON',
    `example_outputs`  json             NOT NULL COMMENT '示例输出 JSON',
    `created_at`       datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`       datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='脚本技能模板表';

CREATE TABLE `workspaces`
(
    `id`           bigint unsigned  NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name`         varchar(255)     NOT NULL COMMENT '空间名称',
    `description`  text             NOT NULL COMMENT '描述',
    `created_at`   datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   datetime         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY (`name`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='项目空间表';
