"""Templates SQL; transaction ownership is separate."""

from .base import execute


class TemplatesRepository:
    @staticmethod
    def list_templates_select_experiment_templates(db, parameters=()):
        return execute(
            db, "SELECT * FROM experiment_templates WHERE workspace_id=:p0 ORDER BY created DESC, id", parameters
        )

    @staticmethod
    def create_template_insert_experiment_templates(db, parameters=()):
        return execute(
            db,
            "INSERT INTO experiment_templates(id,workspace_id,owner_id,name,config,created)  VALUES (:id,:workspace_id,:owner_id,:name,:config,:created)",
            parameters,
        )

    @staticmethod
    def create_template_select_experiment_templates(db, parameters=()):
        return execute(db, "SELECT name FROM experiment_templates WHERE workspace_id=:p0", parameters)

    @staticmethod
    def delete_template_delete_experiment_templates(db, parameters=()):
        return execute(db, "DELETE FROM experiment_templates WHERE id=:p0", parameters)

    @staticmethod
    def delete_template_select_experiment_templates(db, parameters=()):
        return execute(db, "SELECT * FROM experiment_templates WHERE id=:p0 AND workspace_id=:p1", parameters)
