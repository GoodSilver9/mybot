#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify API 통합 모듈
기존 디스코드 봇에 Spotify 기능 추가
"""

import aiohttp
import asyncio
import json
import os
from typing import Optional, List, Dict
import base64

class SpotifyAPI:
    def __init__(self):
        self.client_id = os.getenv('SPOTIFY_CLIENT_ID', '')
        self.client_secret = os.getenv('SPOTIFY_CLIENT_SECRET', '')
        self.access_token = None
        self.token_expires_at = 0
        
    async def get_access_token(self) -> bool:
        """Spotify 액세스 토큰 획득"""
        if not self.client_id or not self.client_secret:
            print("Spotify 클라이언트 ID와 시크릿이 설정되지 않았습니다.")
            return False
            
        try:
            # Basic 인증 헤더 생성
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                'Authorization': f'Basic {auth_b64}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'grant_type': 'client_credentials'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://accounts.spotify.com/api/token',
                    headers=headers,
                    data=data
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.access_token = token_data['access_token']
                        self.token_expires_at = asyncio.get_event_loop().time() + token_data['expires_in']
                        return True
                    else:
                        print(f"토큰 획득 실패: {response.status}")
                        return False
                        
        except Exception as e:
            print(f"토큰 획득 중 오류: {e}")
            return False
    
    async def ensure_token(self) -> bool:
        """토큰이 유효한지 확인하고 필요시 갱신"""
        if not self.access_token or asyncio.get_event_loop().time() >= self.token_expires_at:
            return await self.get_access_token()
        return True
    
    async def search_tracks(self, query: str, limit: int = 10) -> List[Dict]:
        """트랙 검색"""
        if not await self.ensure_token():
            return []
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            params = {
                'q': query,
                'type': 'track',
                'limit': limit,
                'market': 'KR'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/search',
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        tracks = []
                        for track in data['tracks']['items']:
                            tracks.append({
                                'name': track['name'],
                                'artist': track['artists'][0]['name'],
                                'album': track['album']['name'],
                                'external_url': track['external_urls']['spotify'],
                                'preview_url': track['preview_url'],
                                'duration_ms': track['duration_ms']
                            })
                        return tracks
                    else:
                        print(f"트랙 검색 실패: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"트랙 검색 중 오류: {e}")
            return []
    
    async def get_recommendations(self, seed_genres: List[str] = None, 
                                seed_artists: List[str] = None,
                                seed_tracks: List[str] = None,
                                target_energy: float = None,
                                target_valence: float = None,
                                limit: int = 10) -> List[Dict]:
        """음악 추천"""
        if not await self.ensure_token():
            return []
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            params = {
                'limit': limit,
                'market': 'KR'
            }
            
            # 최소 하나의 seed는 필수
            if seed_genres:
                params['seed_genres'] = ','.join(seed_genres[:5])
            elif seed_artists:
                params['seed_artists'] = ','.join(seed_artists[:5])
            elif seed_tracks:
                params['seed_tracks'] = ','.join(seed_tracks[:5])
            else:
                # seed가 없으면 기본값 추가
                params['seed_genres'] = 'pop'
            
            if target_energy is not None:
                params['target_energy'] = target_energy
            if target_valence is not None:
                params['target_valence'] = target_valence
            
            print(f"[디버그] Spotify API 요청 파라미터: {params}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/recommendations',
                    headers=headers,
                    params=params
                ) as response:
                    print(f"[디버그] Spotify API 응답 상태: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        tracks = []
                        for track in data['tracks']:
                            tracks.append({
                                'name': track['name'],
                                'artist': track['artists'][0]['name'],
                                'album': track['album']['name'],
                                'external_url': track['external_urls']['spotify'],
                                'preview_url': track['preview_url'],
                                'duration_ms': track['duration_ms']
                            })
                        return tracks
                    else:
                        error_text = await response.text()
                        print(f"추천 실패: {response.status}, 응답: {error_text}")
                        return []
                        
        except Exception as e:
            print(f"추천 중 오류: {e}")
            return []
    
    async def get_available_genres(self) -> List[str]:
        """사용 가능한 장르 목록 가져오기"""
        if not await self.ensure_token():
            return []
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/recommendations/available-genre-seeds',
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['genres']
                    else:
                        print(f"장르 목록 가져오기 실패: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"장르 목록 가져오기 중 오류: {e}")
            return []

    async def test_spotify_connection(self) -> bool:
        """Spotify API 연결 테스트"""
        if not await self.ensure_token():
            return False
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            # 간단한 검색 API 테스트
            params = {
                'q': 'BTS',
                'type': 'artist',
                'limit': 1
            }
            
            print(f"[디버그] Spotify 연결 테스트 시작")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/search',
                    headers=headers,
                    params=params
                ) as response:
                    print(f"[디버그] 검색 API 응답 상태: {response.status}")
                    if response.status == 200:
                        print("[디버그] Spotify API 연결 성공!")
                        return True
                    else:
                        error_text = await response.text()
                        print(f"[디버그] 검색 API 실패: {response.status}, 응답: {error_text}")
                        return False
                        
        except Exception as e:
            print(f"[디버그] 연결 테스트 중 오류: {e}")
            return False

    async def search_and_recommend(self, query: str, limit: int = 5) -> List[Dict]:
        """검색을 통한 추천 (권한 문제 우회)"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            params = {
                'q': query,
                'type': 'track',
                'limit': limit,
                'market': 'KR'
            }
            
            print(f"[디버그] 검색 기반 추천: {query}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/search',
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        tracks = []
                        for track in data['tracks']['items']:
                            tracks.append({
                                'name': track['name'],
                                'artist': track['artists'][0]['name'],
                                'album': track['album']['name'],
                                'external_url': track['external_urls']['spotify'],
                                'preview_url': track['preview_url'],
                                'duration_ms': track['duration_ms']
                            })
                        return tracks
                    else:
                        print(f"검색 실패: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"검색 중 오류: {e}")
            return []

    async def get_similar_tracks(self, track_name: str, artist_name: str, limit: int = 5) -> List[Dict]:
        """현재 재생 중인 곡과 비슷한 음악 추천"""
        if not await self.ensure_token():
            return []
            
        try:
            # 먼저 현재 곡을 검색해서 Spotify ID를 찾기
            search_query = f"{track_name} {artist_name}"
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            params = {
                'q': search_query,
                'type': 'track',
                'limit': 1,
                'market': 'KR'
            }
            
            print(f"[디버그] 비슷한 곡 찾기 - 검색: {search_query}")
            
            async with aiohttp.ClientSession() as session:
                # 1단계: 현재 곡 검색
                async with session.get(
                    'https://api.spotify.com/v1/search',
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data['tracks']['items']:
                            track_id = data['tracks']['items'][0]['id']
                            print(f"[디버그] 곡 ID 찾음: {track_id}")
                            
                            # 2단계: 비슷한 곡 추천 (여러 방법 시도)
                            # 방법 1: seed_tracks만 사용
                            rec_params = {
                                'seed_tracks': track_id,
                                'limit': limit,
                                'market': 'KR'
                            }
                            
                            async with session.get(
                                'https://api.spotify.com/v1/recommendations',
                                headers=headers,
                                params=rec_params
                            ) as rec_response:
                                if rec_response.status == 200:
                                    rec_data = await rec_response.json()
                                    tracks = []
                                    for track in rec_data['tracks']:
                                        tracks.append({
                                            'name': track['name'],
                                            'artist': track['artists'][0]['name'],
                                            'album': track['album']['name'],
                                            'external_url': track['external_urls']['spotify'],
                                            'preview_url': track['preview_url'],
                                            'duration_ms': track['duration_ms']
                                        })
                                    print(f"[디버그] 비슷한 곡 {len(tracks)}개 찾음")
                                    return tracks
                                else:
                                    print(f"[디버그] 추천 API 실패 (seed_tracks): {rec_response.status}")
                                    
                                    # 방법 2: 아티스트 기반 추천 시도
                                    try:
                                        # 아티스트 ID 찾기
                                        artist_params = {
                                            'q': artist_name,
                                            'type': 'artist',
                                            'limit': 1,
                                            'market': 'KR'
                                        }
                                        
                                        async with session.get(
                                            'https://api.spotify.com/v1/search',
                                            headers=headers,
                                            params=artist_params
                                        ) as artist_response:
                                            if artist_response.status == 200:
                                                artist_data = await artist_response.json()
                                                if artist_data['artists']['items']:
                                                    artist_id = artist_data['artists']['items'][0]['id']
                                                    print(f"[디버그] 아티스트 ID 찾음: {artist_id}")
                                                    
                                                    # 아티스트 기반 추천
                                                    artist_rec_params = {
                                                        'seed_artists': artist_id,
                                                        'limit': limit,
                                                        'market': 'KR'
                                                    }
                                                    
                                                    async with session.get(
                                                        'https://api.spotify.com/v1/recommendations',
                                                        headers=headers,
                                                        params=artist_rec_params
                                                    ) as artist_rec_response:
                                                        if artist_rec_response.status == 200:
                                                            artist_rec_data = await artist_rec_response.json()
                                                            tracks = []
                                                            for track in artist_rec_data['tracks']:
                                                                tracks.append({
                                                                    'name': track['name'],
                                                                    'artist': track['artists'][0]['name'],
                                                                    'album': track['album']['name'],
                                                                    'external_url': track['external_urls']['spotify'],
                                                                    'preview_url': track['preview_url'],
                                                                    'duration_ms': track['duration_ms']
                                                                })
                                                            print(f"[디버그] 아티스트 기반 비슷한 곡 {len(tracks)}개 찾음")
                                                            return tracks
                                                        else:
                                                            print(f"[디버그] 아티스트 기반 추천 실패: {artist_rec_response.status}")
                                    except Exception as e:
                                        print(f"[디버그] 아티스트 기반 추천 중 오류: {e}")
                                    
                                    # 방법 3: 검색 기반 추천으로 대체
                                    print(f"[디버그] 검색 기반 추천으로 대체")
                                    # 여러 검색어 시도
                                    search_queries = [
                                        f"{artist_name} similar",
                                        f"{artist_name} songs",
                                        f"{track_name} similar",
                                        f"{artist_name} popular",
                                        f"{artist_name} hits"
                                    ]
                                    
                                    for query in search_queries:
                                        result = await self.search_and_recommend(query, limit)
                                        if result:
                                            print(f"[디버그] 검색 성공: {query}")
                                            return result
                                    
                                    # 모든 검색이 실패하면 빈 리스트 반환
                                    print(f"[디버그] 모든 검색 실패")
                                    return []
                        else:
                            print(f"[디버그] 곡을 찾을 수 없음: {search_query}")
                            # 곡을 찾을 수 없으면 아티스트로 검색
                            return await self.search_and_recommend(f"{artist_name} songs", limit)
                    else:
                        print(f"[디버그] 검색 실패: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"[디버그] 비슷한 곡 찾기 중 오류: {e}")
            return []

    async def get_playlist_tracks(self, playlist_url: str, limit: int = 10) -> tuple[List[Dict], Dict]:
        """플레이리스트에서 트랙 목록 가져오기 (랜덤 샘플링)"""
        if not await self.ensure_token():
            return [], {}
            
        try:
            # 플레이리스트 ID 추출
            playlist_id = self._extract_playlist_id(playlist_url)
            if not playlist_id:
                print(f"[디버그] 플레이리스트 ID 추출 실패: {playlist_url}")
                return [], {}
            
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            async with aiohttp.ClientSession() as session:
                # 1단계: 플레이리스트 기본 정보 가져오기
                playlist_info_url = f'https://api.spotify.com/v1/playlists/{playlist_id}'
                async with session.get(playlist_info_url, headers=headers) as response:
                    if response.status != 200:
                        print(f"[디버그] 플레이리스트 정보 조회 실패: {response.status}")
                        return [], {}
                    
                    playlist_data = await response.json()
                    playlist_info = {
                        'name': playlist_data['name'],
                        'description': playlist_data.get('description', ''),
                        'total_tracks': playlist_data['tracks']['total'],
                        'external_url': playlist_data['external_urls']['spotify']
                    }
                
                # 2단계: 모든 트랙 가져오기 (페이징 처리)
                all_tracks = []
                tracks_url = f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks'
                offset = 0
                limit_per_request = 100  # Spotify API 최대값
                
                while True:
                    params = {
                        'limit': limit_per_request,
                        'offset': offset,
                        'market': 'KR'
                    }
                    
                    async with session.get(tracks_url, headers=headers, params=params) as response:
                        if response.status != 200:
                            print(f"[디버그] 트랙 목록 조회 실패: {response.status}")
                            break
                        
                        data = await response.json()
                        tracks = data['items']
                        
                        if not tracks:
                            break
                        
                        # 트랙 정보 추출
                        for item in tracks:
                            if item['track'] and item['track']['type'] == 'track':  # 트랙이 존재하고 삭제되지 않은 경우
                                track = item['track']
                                all_tracks.append({
                                    'name': track['name'],
                                    'artist': track['artists'][0]['name'],
                                    'album': track['album']['name'],
                                    'external_url': track['external_urls']['spotify'],
                                    'preview_url': track['preview_url'],
                                    'duration_ms': track['duration_ms']
                                })
                        
                        # 더 이상 가져올 트랙이 없으면 중단
                        if len(tracks) < limit_per_request:
                            break
                        
                        offset += limit_per_request
                
                print(f"[디버그] 플레이리스트에서 총 {len(all_tracks)}개 트랙 발견")
                
                # 3단계: 랜덤 샘플링
                import random
                if len(all_tracks) <= limit:
                    selected_tracks = all_tracks
                else:
                    selected_tracks = random.sample(all_tracks, limit)
                
                print(f"[디버그] 랜덤으로 {len(selected_tracks)}개 트랙 선택")
                return selected_tracks, playlist_info
                
        except Exception as e:
            print(f"[디버그] 플레이리스트 트랙 조회 중 오류: {e}")
            return [], {}
    
    def _extract_playlist_id(self, playlist_url: str) -> str:
        """플레이리스트 URL에서 ID 추출"""
        try:
            # Spotify URL 패턴들
            patterns = [
                r'playlist/([a-zA-Z0-9]+)',
                r'playlist:([a-zA-Z0-9]+)',
                r'open\.spotify\.com/playlist/([a-zA-Z0-9]+)'
            ]
            
            import re
            for pattern in patterns:
                match = re.search(pattern, playlist_url)
                if match:
                    return match.group(1)
            
            # URL이 아니라 ID인 경우
            if len(playlist_url) == 22 and playlist_url.replace('-', '').replace('_', '').isalnum():
                return playlist_url
            
            return None
            
        except Exception as e:
            print(f"[디버그] 플레이리스트 ID 추출 중 오류: {e}")
            return None

# 감정 분석을 위한 간단한 키워드 매핑
EMOTION_KEYWORDS = {
    # 기본 감정 (8개)
    '기쁨': {'energy': 0.8, 'valence': 0.8, 'genres': ['pop', 'dance', 'k-pop']},
    '슬픔': {'energy': 0.3, 'valence': 0.2, 'genres': ['sad', 'acoustic', 'ballad']},
    '화남': {'energy': 0.7, 'valence': 0.3, 'genres': ['rock', 'metal', 'punk']},
    '평온': {'energy': 0.4, 'valence': 0.6, 'genres': ['ambient', 'chill', 'lofi']},
    '신남': {'energy': 0.9, 'valence': 0.9, 'genres': ['edm', 'dance', 'electronic']},
    '잔잔': {'energy': 0.2, 'valence': 0.5, 'genres': ['acoustic', 'folk', 'indie']},
    '활기': {'energy': 0.8, 'valence': 0.7, 'genres': ['pop', 'funk', 'disco']},
    '힘듦': {'energy': 0.4, 'valence': 0.3, 'genres': ['indie', 'alternative', 'emo']},
    
    # 추가 감정 (8개)
    '사랑': {'energy': 0.6, 'valence': 0.8, 'genres': ['pop', 'r-n-b', 'ballad']},
    '설렘': {'energy': 0.7, 'valence': 0.8, 'genres': ['pop', 'k-pop', 'dance']},
    '우울': {'energy': 0.2, 'valence': 0.1, 'genres': ['sad', 'ambient', 'indie']},
    '분노': {'energy': 0.8, 'valence': 0.2, 'genres': ['rock', 'metal', 'hardcore']},
    '스트레스': {'energy': 0.5, 'valence': 0.3, 'genres': ['chill', 'ambient', 'classical']},
    '피곤': {'energy': 0.2, 'valence': 0.4, 'genres': ['ambient', 'lofi', 'chill']},
    '외로움': {'energy': 0.3, 'valence': 0.2, 'genres': ['sad', 'ballad', 'indie']},
    '희망': {'energy': 0.7, 'valence': 0.8, 'genres': ['pop', 'rock', 'indie']},
    
    # 상황별 (8개)
    '운동': {'energy': 0.9, 'valence': 0.7, 'genres': ['workout', 'edm', 'hip-hop']},
    '공부': {'energy': 0.3, 'valence': 0.5, 'genres': ['lofi', 'ambient', 'classical']},
    '잠': {'energy': 0.1, 'valence': 0.4, 'genres': ['ambient', 'lofi', 'chill']},
    '드라이브': {'energy': 0.6, 'valence': 0.7, 'genres': ['pop', 'rock', 'indie']},
    '파티': {'energy': 0.9, 'valence': 0.9, 'genres': ['edm', 'dance', 'pop']},
    '요리': {'energy': 0.5, 'valence': 0.6, 'genres': ['jazz', 'lofi', 'chill']},
    '샤워': {'energy': 0.4, 'valence': 0.6, 'genres': ['pop', 'indie', 'chill']},
    '청소': {'energy': 0.7, 'valence': 0.6, 'genres': ['pop', 'dance', 'funk']},
    
    # 장르별 (8개)
    '힙합': {'energy': 0.7, 'valence': 0.6, 'genres': ['hip-hop', 'rap', 'trap']},
    '발라드': {'energy': 0.3, 'valence': 0.4, 'genres': ['ballad', 'acoustic', 'folk']},
    '댄스': {'energy': 0.8, 'valence': 0.8, 'genres': ['dance', 'edm', 'pop']},
    '락': {'energy': 0.8, 'valence': 0.6, 'genres': ['rock', 'alternative', 'punk']},
    '재즈': {'energy': 0.5, 'valence': 0.6, 'genres': ['jazz', 'blues', 'soul']},
    '클래식': {'energy': 0.4, 'valence': 0.5, 'genres': ['classical', 'orchestral']},
    '일렉트로닉': {'energy': 0.7, 'valence': 0.6, 'genres': ['electronic', 'edm', 'techno']},
    '컨트리': {'energy': 0.6, 'valence': 0.7, 'genres': ['country', 'folk', 'americana']},
    
    # 계절별 (4개)
    '봄': {'energy': 0.6, 'valence': 0.7, 'genres': ['pop', 'indie', 'folk']},
    '여름': {'energy': 0.8, 'valence': 0.8, 'genres': ['pop', 'dance', 'edm']},
    '가을': {'energy': 0.4, 'valence': 0.5, 'genres': ['indie', 'folk', 'acoustic']},
    '겨울': {'energy': 0.3, 'valence': 0.4, 'genres': ['ambient', 'chill', 'indie']},
    
    # 시간대별 (4개)
    '아침': {'energy': 0.6, 'valence': 0.7, 'genres': ['pop', 'indie', 'chill']},
    '점심': {'energy': 0.7, 'valence': 0.6, 'genres': ['pop', 'rock', 'indie']},
    '저녁': {'energy': 0.5, 'valence': 0.6, 'genres': ['jazz', 'lofi', 'chill']},
    '밤': {'energy': 0.3, 'valence': 0.4, 'genres': ['ambient', 'lofi', 'chill']},
    
    # 특별한 상황 (8개)
    '이별': {'energy': 0.2, 'valence': 0.1, 'genres': ['sad', 'ballad', 'indie']},
    '고백': {'energy': 0.5, 'valence': 0.8, 'genres': ['pop', 'ballad', 'r-n-b']},
    '생일': {'energy': 0.8, 'valence': 0.9, 'genres': ['pop', 'dance', 'k-pop']},
    '졸업': {'energy': 0.6, 'valence': 0.7, 'genres': ['pop', 'indie', 'rock']},
    '취업': {'energy': 0.7, 'valence': 0.8, 'genres': ['pop', 'rock', 'indie']},
    '여행': {'energy': 0.7, 'valence': 0.8, 'genres': ['pop', 'indie', 'folk']},
    '데이트': {'energy': 0.6, 'valence': 0.8, 'genres': ['pop', 'r-n-b', 'jazz']},
    '결혼': {'energy': 0.7, 'valence': 0.9, 'genres': ['pop', 'ballad', 'classical']},
    
    # 한국어 특화 (8개)
    '들뜬': {'energy': 0.8, 'valence': 0.8, 'genres': ['k-pop', 'pop', 'dance']},
    '우울한': {'energy': 0.2, 'valence': 0.1, 'genres': ['sad', 'ballad', 'indie']},
    '신나는': {'energy': 0.9, 'valence': 0.9, 'genres': ['k-pop', 'dance', 'edm']},
    '잔잔한': {'energy': 0.2, 'valence': 0.5, 'genres': ['ballad', 'acoustic', 'indie']},
    '활기찬': {'energy': 0.8, 'valence': 0.7, 'genres': ['k-pop', 'pop', 'funk']},
    '힘든': {'energy': 0.4, 'valence': 0.3, 'genres': ['indie', 'alternative', 'emo']},
    '편안한': {'energy': 0.3, 'valence': 0.6, 'genres': ['chill', 'ambient', 'lofi']},
    '격렬한': {'energy': 0.9, 'valence': 0.5, 'genres': ['rock', 'metal', 'hardcore']},
    
    # 음악 특성 (6개)
    '빠른': {'energy': 0.8, 'valence': 0.7, 'genres': ['dance', 'edm', 'rock']},
    '느린': {'energy': 0.2, 'valence': 0.4, 'genres': ['ballad', 'ambient', 'chill']},
    '로맨틱': {'energy': 0.5, 'valence': 0.8, 'genres': ['pop', 'ballad', 'r-n-b']},
    '비트': {'energy': 0.8, 'valence': 0.7, 'genres': ['hip-hop', 'edm', 'dance']},
    '멜로디': {'energy': 0.5, 'valence': 0.6, 'genres': ['pop', 'indie', 'folk']},
    '리듬': {'energy': 0.7, 'valence': 0.6, 'genres': ['funk', 'disco', 'dance']}
}

SIMILAR_WORDS = {
    # 기쁨 관련
    '승무': ['기쁨', '활기', '신남'],
    '들뜨고': ['기쁨', '신남', '설렘'],
    '들뜬': ['기쁨', '신남', '설렘'],
    '신나고': ['신남', '기쁨', '활기'],
    '신나': ['신남', '기쁨', '활기'],
    '즐겁고': ['기쁨', '신남', '활기'],
    '즐거워': ['기쁨', '신남', '활기'],
    '행복해': ['기쁨', '사랑', '희망'],
    '행복하고': ['기쁨', '사랑', '희망'],
    '좋아': ['기쁨', '평온', '편안한'],
    '좋고': ['기쁨', '평온', '편안한'],
    
    # 슬픔 관련
    '슬프고': ['슬픔', '우울', '외로움'],
    '슬퍼': ['슬픔', '우울', '외로움'],
    '우울하고': ['우울', '슬픔', '외로움'],
    '우울해': ['우울', '슬픔', '외로움'],
    '외롭고': ['외로움', '슬픔', '우울'],
    '외로워': ['외로움', '슬픔', '우울'],
    '쓸쓸하고': ['외로움', '슬픔', '우울'],
    '쓸쓸해': ['외로움', '슬픔', '우울'],
    '허전하고': ['외로움', '슬픔', '우울'],
    '허전해': ['외로움', '슬픔', '우울'],
    
    # 화남 관련
    '화나고': ['화남', '분노', '스트레스'],
    '화나': ['화남', '분노', '스트레스'],
    '짜증나고': ['화남', '분노', '스트레스'],
    '짜증나': ['화남', '분노', '스트레스'],
    '열받고': ['화남', '분노', '스트레스'],
    '열받아': ['화남', '분노', '스트레스'],
    '분노하고': ['분노', '화남', '스트레스'],
    '분노해': ['분노', '화남', '스트레스'],
    
    # 스트레스 관련
    '스트레스 받고': ['스트레스', '피곤', '힘듦'],
    '스트레스 받아': ['스트레스', '피곤', '힘듦'],
    '복잡하고': ['스트레스', '힘듦', '우울'],
    '복잡해': ['스트레스', '힘듦', '우울'],
    '괴롭고': ['스트레스', '힘듦', '우울'],
    '괴로워': ['스트레스', '힘듦', '우울'],
    '답답하고': ['스트레스', '힘듦', '우울'],
    '답답해': ['스트레스', '힘듦', '우울'],
    
    # 피곤 관련
    '피곤하고': ['피곤', '스트레스', '힘듦'],
    '피곤해': ['피곤', '스트레스', '힘듦'],
    '지치고': ['피곤', '스트레스', '힘듦'],
    '지쳐': ['피곤', '스트레스', '힘듦'],
    '힘들고': ['힘듦', '피곤', '스트레스'],
    '힘들어': ['힘듦', '피곤', '스트레스'],
    '버겁고': ['힘듦', '피곤', '스트레스'],
    '버거워': ['힘듦', '피곤', '스트레스'],
    
    # 평온/편안 관련
    '평온하고': ['평온', '편안한', '잔잔'],
    '평온해': ['평온', '편안한', '잔잔'],
    '편안하고': ['편안한', '평온', '잔잔'],
    '편안해': ['편안한', '평온', '잔잔'],
    '차분하고': ['평온', '편안한', '잔잔'],
    '차분해': ['평온', '편안한', '잔잔'],
    '고요하고': ['평온', '편안한', '잔잔'],
    '고요해': ['평온', '편안한', '잔잔'],
    
    # 활기 관련
    '활기차고': ['활기', '기쁨', '신남'],
    '활기차': ['활기', '기쁨', '신남'],
    '경쾌하고': ['활기', '기쁨', '신남'],
    '경쾌해': ['활기', '기쁨', '신남'],
    '상쾌하고': ['활기', '기쁨', '신남'],
    '상쾌해': ['활기', '기쁨', '신남'],
    
    # 잔잔 관련
    '잔잔하고': ['잔잔', '평온', '편안한'],
    '잔잔해': ['잔잔', '평온', '편안한'],
    '조용하고': ['잔잔', '평온', '편안한'],
    '조용해': ['잔잔', '평온', '편안한'],
    '고요하고': ['잔잔', '평온', '편안한'],
    '고요해': ['잔잔', '평온', '편안한'],
    
    # 사랑 관련
    '사랑스럽고': ['사랑', '로맨틱', '설렘'],
    '사랑스러워': ['사랑', '로맨틱', '설렘'],
    '설렘': ['설렘', '사랑', '로맨틱'],
    '설레고': ['설렘', '사랑', '로맨틱'],
    '설레': ['설렘', '사랑', '로맨틱'],
    '두근두근': ['설렘', '사랑', '로맨틱'],
    '떨리고': ['설렘', '사랑', '로맨틱'],
    '떨려': ['설렘', '사랑', '로맨틱'],
    
    # 희망 관련
    '희망적이고': ['희망', '기쁨', '활기'],
    '희망적이야': ['희망', '기쁨', '활기'],
    '기대되고': ['희망', '기쁨', '활기'],
    '기대돼': ['희망', '기쁨', '활기'],
    '미래가': ['희망', '기쁨', '활기'],
    '앞날이': ['희망', '기쁨', '활기'],
    
    # 상황별 유사어
    '들뜨고 싶어': ['기쁨', '신남', '활기'],
    '신나고 싶어': ['신남', '기쁨', '활기'],
    '기분 전환': ['활기', '기쁨', '신남'],
    '기분 좋게': ['기쁨', '신남', '활기'],
    '기분 나쁘게': ['슬픔', '우울', '화남'],
    '스트레스 풀고': ['편안한', '평온', '잔잔'],
    '긴장 풀고': ['편안한', '평온', '잔잔'],
    '마음 진정': ['편안한', '평온', '잔잔'],
    
    # 음악 특성 유사어
    '빠르게': ['빠른', '활기', '신남'],
    '느리게': ['느린', '잔잔', '편안한'],
    '로맨틱하게': ['로맨틱', '사랑', '설렘'],
    '비트 있게': ['비트', '활기', '신남'],
    '멜로디 좋게': ['멜로디', '잔잔', '편안한'],
    '리듬 있게': ['리듬', '활기', '신남'],
    
    # 장르 유사어
    '힙합처럼': ['힙합', '비트', '활기'],
    '발라드처럼': ['발라드', '잔잔', '로맨틱'],
    '댄스처럼': ['댄스', '활기', '신남'],
    '락처럼': ['락', '격렬한', '화남'],
    '재즈처럼': ['재즈', '편안한', '평온'],
    '클래식처럼': ['클래식', '잔잔', '편안한'],
    
    # 계절 유사어
    '봄날': ['봄', '기쁨', '활기'],
    '여름날': ['여름', '신남', '활기'],
    '가을날': ['가을', '잔잔', '편안한'],
    '겨울날': ['겨울', '잔잔', '편안한'],
    
    # 시간대 유사어
    '아침에': ['아침', '기쁨', '활기'],
    '점심에': ['점심', '활기', '기쁨'],
    '저녁에': ['저녁', '편안한', '잔잔'],
    '밤에': ['밤', '잔잔', '편안한'],
    
    # 특별한 상황 유사어
    '이별할 때': ['이별', '슬픔', '우울'],
    '고백할 때': ['고백', '설렘', '로맨틱'],
    '생일 축하': ['생일', '기쁨', '신남'],
    '졸업할 때': ['졸업', '희망', '기쁨'],
    '취업할 때': ['취업', '희망', '기쁨'],
    '여행갈 때': ['여행', '기쁨', '활기'],
    '데이트할 때': ['데이트', '로맨틱', '사랑'],
    '결혼할 때': ['결혼', '사랑', '로맨틱']
}
async def analyze_emotion_and_recommend(text: str, spotify_api: SpotifyAPI) -> List[Dict]:
    """텍스트에서 감정을 분석하고 Spotify 추천"""
    print(f"[디버그] 감정 분석 시작: {text}")
    
    # 먼저 연결 테스트
    if not await spotify_api.test_spotify_connection():
        print("[디버그] Spotify API 연결 실패")
        return []
    
    text_lower = text.lower()
    
    # 감정에 따른 검색어 매핑
    emotion_queries = {
        '기쁨': 'happy korean pop',
        '슬픔': 'sad korean ballad',
        '신남': 'energetic korean dance',
        '잔잔': 'calm korean acoustic',
        '활기': 'upbeat korean pop',
        '사랑': 'romantic korean ballad',
        '설렘': 'excited korean pop',
        '우울': 'melancholy korean indie',
        '스트레스': 'relaxing korean chill',
        '피곤': 'sleepy korean ambient'
    }
    
    # 1단계: 정확한 키워드 매칭
    for emotion, query in emotion_queries.items():
        if emotion in text_lower:
            print(f"[디버그] 정확한 감정 매칭: {emotion}")
            return await spotify_api.search_and_recommend(query, 5)
    
    # 2단계: 유사어 매칭 (부분 문자열 검색으로 개선)
    for similar_word, emotions in SIMILAR_WORDS.items():
        if similar_word in text_lower:  # 부분 문자열 검색
            emotion = emotions[0]
            if emotion in emotion_queries:
                print(f"[디버그] 유사어 매칭: '{similar_word}' → {emotion}")
                return await spotify_api.search_and_recommend(emotion_queries[emotion], 5)
    
    # 3단계: 기본 검색
    print("[디버그] 기본 검색으로 fallback")
    return await spotify_api.search_and_recommend('korean pop', 5)

# 전역 Spotify API 인스턴스
spotify_api = SpotifyAPI() 