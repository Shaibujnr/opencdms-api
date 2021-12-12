import datetime
import json
import pytest
from sqlalchemy.sql import text as sa_text
from sqlalchemy.orm.session import sessionmaker
from opencdms.models.climsoft import v4_1_1_core as climsoft_models
from apps.climsoft.db.engine import db_engine
from apps.climsoft.schemas import physicalfeatureclass_schema
from tests.datagen.climsoft import physicalfeatureclass as climsoft_physical_feature_class, station as climsoft_station
from faker import Faker
from fastapi.testclient import TestClient
from apps.auth.db.engine import db_engine as auth_db_engine
from apps.auth.db.models import user_model
from passlib.hash import django_pbkdf2_sha256 as handler


fake = Faker()


def setup_module(module):
    with auth_db_engine.connect().execution_options(autocommit=True) as connection:
        with connection.begin():
            auth_db_engine.execute(sa_text(f'''
                TRUNCATE TABLE {user_model.AuthUser.__tablename__} RESTART IDENTITY CASCADE
            ''').execution_options(autocommit=True))

    with db_engine.connect().execution_options(autocommit=True) as connection:
        with connection.begin():
            db_engine.execute(sa_text(f"""
                SET FOREIGN_KEY_CHECKS = 0;
                TRUNCATE TABLE {climsoft_models.Physicalfeatureclas.__tablename__};
                TRUNCATE TABLE {climsoft_models.Station.__tablename__};
                SET FOREIGN_KEY_CHECKS = 1;
            """))

    Session = sessionmaker(bind=db_engine)
    db_session = Session()

    for i in range(1, 11):
        station = climsoft_models.Station(
            **climsoft_station.get_valid_station_input().dict()
        )
        db_session.add(station)
        db_session.commit()

        db_session.add(climsoft_models.Physicalfeatureclas(
            **climsoft_physical_feature_class.get_valid_physical_feature_class_input(station_id=station.stationId).dict()
        ))
        db_session.commit()
    db_session.close()

    AuthSession = sessionmaker(bind=auth_db_engine)
    auth_session = AuthSession()
    user = user_model.AuthUser(
        username="testuser",
        password=handler.hash("password"),
        first_name=fake.first_name(),
        last_name=fake.last_name(),
        email=fake.email()
    )
    auth_session.add(user)
    auth_session.commit()
    auth_session.close()


def teardown_module(module):
    with auth_db_engine.connect().execution_options(autocommit=True) as connection:
        with connection.begin():
            auth_db_engine.execute(sa_text(f'''
                TRUNCATE TABLE {user_model.AuthUser.__tablename__} RESTART IDENTITY CASCADE
            ''').execution_options(autocommit=True))

    with db_engine.connect().execution_options(autocommit=True) as connection:
        with connection.begin():
            db_engine.execute(sa_text(f"""
                SET FOREIGN_KEY_CHECKS = 0;
                TRUNCATE TABLE {climsoft_models.Physicalfeatureclas.__tablename__};
                TRUNCATE TABLE {climsoft_models.Station.__tablename__};
                SET FOREIGN_KEY_CHECKS = 1;
            """))


@pytest.fixture
def get_access_token(test_app: TestClient):
    sign_in_data = {"username": "testuser", "password": "password", "scope": ""}
    response = test_app.post("/api/auth/v1/sign-in", data=sign_in_data)
    response_data = response.json()
    return response_data['access_token']


@pytest.fixture
def get_station():
    Session = sessionmaker(bind=db_engine)
    session = Session()
    station = climsoft_models.Station(**climsoft_station.get_valid_station_input().dict())
    session.add(station)
    session.commit()
    yield station
    session.close()


@pytest.fixture
def get_physical_feature_class(get_station: climsoft_models.Station):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    physical_feature_class = climsoft_models.Physicalfeatureclas(**climsoft_physical_feature_class.get_valid_physical_feature_class_input(station_id=get_station.stationId).dict())
    session.add(physical_feature_class)
    session.commit()
    yield physical_feature_class
    session.close()


def test_should_return_first_five_physical_feature_class(test_app: TestClient, get_access_token: str):
    response = test_app.get("/api/climsoft/v1/physical-feature-class", params={"limit": 5}, headers={
        "Authorization": f"Bearer {get_access_token}"
    })
    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data["result"]) == 5


def test_should_return_single_physical_feature_class(test_app: TestClient, get_physical_feature_class: climsoft_models.Physicalfeatureclas, get_access_token: str):
    response = test_app.get(f"/api/climsoft/v1/physical-feature-class/{get_physical_feature_class.featureClass}", headers={
        "Authorization": f"Bearer {get_access_token}"
    })
    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data["result"]) == 1


def test_should_create_a_physical_feature_class(test_app: TestClient, get_station: climsoft_models.Station, get_access_token: str):
    physical_feature_class_data = climsoft_physical_feature_class.get_valid_physical_feature_class_input(station_id=get_station.stationId).dict(by_alias=True)
    response = test_app.post("/api/climsoft/v1/physical-feature-class", data=json.dumps(physical_feature_class_data, default=str), headers={
        "Authorization": f"Bearer {get_access_token}"
    })
    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data["result"]) == 1


def test_should_raise_validation_error(test_app: TestClient, get_station: climsoft_models.Station, get_access_token: str):
    physical_feature_class_data = climsoft_physical_feature_class.get_valid_physical_feature_class_input(station_id=get_station.stationId).dict()
    response = test_app.post("/api/climsoft/v1/physical-feature-class", data=json.dumps(physical_feature_class_data, default=str), headers={
        "Authorization": f"Bearer {get_access_token}"
    })
    assert response.status_code == 422


def test_should_update_physical_feature_class(test_app: TestClient, get_physical_feature_class: climsoft_models.Physicalfeatureclas, get_access_token: str):
    physical_feature_class_data = physicalfeatureclass_schema.PhysicalFeatureClass.from_orm(get_physical_feature_class).dict(by_alias=True)
    feature_class = physical_feature_class_data.pop("feature_class")
    updates = {**physical_feature_class_data, "description": "updated description"}

    response = test_app.put(f"/api/climsoft/v1/physical-feature-class/{feature_class}", data=json.dumps(updates, default=str), headers={
        "Authorization": f"Bearer {get_access_token}"
    })
    response_data = response.json()

    assert response.status_code == 200
    assert response_data["result"][0]["description"] == updates["description"]


def test_should_delete_physical_feature_class(test_app: TestClient, get_physical_feature_class, get_access_token: str):
    physical_feature_class_data = physicalfeatureclass_schema.PhysicalFeatureClass.from_orm(get_physical_feature_class).dict(by_alias=True)
    feature_class = physical_feature_class_data.pop("feature_class")

    response = test_app.delete(f"/api/climsoft/v1/physical-feature-class/{feature_class}", headers={
        "Authorization": f"Bearer {get_access_token}"
    })
    assert response.status_code == 200

    response = test_app.get(f"/api/climsoft/v1/physical-feature-class/{feature_class}", headers={
        "Authorization": f"Bearer {get_access_token}"
    })

    assert response.status_code == 404
